# Future work: Google authentication

This document captures the full design for Google auth in the Ragnerock Python SDK. It is intentionally self-contained so whoever picks this up can implement without re-deriving anything. Nothing here is shipped yet — only password auth is in the current build.

## Ground truth from the OpenAPI spec

Ragnerock exposes exactly **one** Google endpoint:

- `POST /api/auth/google`
  - Body: `{ "credential": "<Google ID token JWT>", "utm_source": ..., "utm_medium": ..., "utm_campaign": ..., "utm_term": ..., "utm_content": ..., "referrer": ... }` — only `credential` is required.
  - Response: `{ "access_token": "...", "token_type": "bearer" }` — same shape as password login.
  - Behavior: server verifies the Google JWT, matches (or creates) the Ragnerock user, returns a bearer token.

There is **no** server-side browser flow: no `/authorize`, no `/callback`, no device code, no auth-code exchange. The SDK has to obtain the Google ID token itself and hand it to Ragnerock.

## Overall approach

The SDK will run the standard OAuth 2.0 Authorization Code flow with PKCE against Google's own endpoints, obtain a Google ID token, then POST it to `/api/auth/google`. Same pattern as `gcloud`, the GitHub CLI, and most other Python CLIs that authenticate with Google.

## SDK surface

One new factory:

```python
from ragnerock import create_engine_google

engine = create_engine_google(
    host="https://api.ragnerock.com",
    project="my_project",
    mode="browser" | "paste",     # default: "browser"
    credential=None,              # optional: pre-obtained Google ID token
)
```

Three modes:

1. **`mode="browser"` (default).** Open the user's default browser to Google's consent screen, capture the redirect on a random port on `127.0.0.1`, exchange the code for an ID token, post to Ragnerock.

2. **`mode="paste"`.** For SSH / headless environments. Print the Google auth URL; the user opens it elsewhere, signs in, and pastes either the full redirect URL or the ID token back into the terminal. Useful when no browser is available.

3. **`credential=<jwt>`.** Caller already has a Google ID token (e.g. from a service account, a pre-existing session, or a CI system). Skip Google entirely and POST straight to Ragnerock.

If both `mode` and `credential` are passed, `credential` wins and `mode` is ignored.

## Implementation

### Library

Use [`google-auth-oauthlib`](https://pypi.org/project/google-auth-oauthlib/). It has the installed-app flow built in:

```python
from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": CLIENT_ID,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            # NO client_secret — Desktop client + PKCE is a public client.
            "redirect_uris": ["http://127.0.0.1"],
        }
    },
    scopes=["openid", "email", "profile"],
)
credentials = flow.run_local_server(host="127.0.0.1", port=0, open_browser=True)
id_token = credentials.id_token
```

The library handles PKCE, port binding, the local HTTP listener, and the code-exchange. We should not hand-roll it.

Add as an optional dep:

```toml
[project.optional-dependencies]
google = ["google-auth-oauthlib>=1.2"]
```

Users who only use password auth don't pull it in.

### For `mode="paste"`

`google-auth-oauthlib` doesn't ship an out-of-band helper as cleanly. The simplest path:

1. Build the auth URL with `redirect_uri=http://127.0.0.1` (or the OOB URN if Google still accepts it for your client — check current status at implementation time).
2. Print the URL; call `input(...)` to get either the full redirect URL or just the `code` query parameter.
3. Exchange the code manually against `https://oauth2.googleapis.com/token`.

Note: Google has been phasing out the OOB flow (`urn:ietf:wg:oauth:2.0:oob`). At implementation time, test whether it still works for Desktop clients; if not, fall back to having the user paste the full `http://127.0.0.1/?code=...&state=...` URL they see after redirect.

### Posting to Ragnerock

Once we have the ID token:

```python
resp = httpx.post(
    f"{host}/api/auth/google",
    json={"credential": id_token},
)
resp.raise_for_status()
access_token = resp.json()["access_token"]
```

From here, the Engine behaves identically to a password-auth engine.

## Client ID — bundling for an open-source package

This is the part that needs the most care.

### Client type: "Desktop app" (installed app)

In the Google Cloud Console, create an OAuth 2.0 client of type **Desktop app**, not "Web application". Desktop clients:
- Are designed for distribution to end users.
- Support PKCE as the security boundary (no client secret required).
- Allow `http://127.0.0.1:{any_port}` redirects without pre-registering each port.
- Are treated by Google as **public** clients — the client ID is not confidential.

### No client_secret

Even though the Cloud Console may hand out a "client secret" when you create a Desktop client, we will **not** use it. PKCE replaces it. Don't embed any client_secret in the package.

(`gcloud` ships a fake-looking `CLOUDSDK_CLIENT_NOTSOSECRET` constant — the variable name is Google's own acknowledgement that it isn't really secret.)

### Shipping the client ID

The client ID is a plain constant in the SDK source, with an env-var override. Put it in its own small module so rotation is easy:

```python
# ragnerock/_google_oauth.py
import os

DEFAULT_CLIENT_ID = "XXXXXXXXXXXX-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.apps.googleusercontent.com"

def client_id() -> str:
    return os.environ.get("RAGNEROCK_GOOGLE_CLIENT_ID", DEFAULT_CLIENT_ID)
```

Checked in, visible on GitHub, fine.

### Scopes

Request only:

```
openid email profile
```

These are **non-sensitive** in Google's scope policy. That means:
- No Google app verification is required before the SDK can be used by external users.
- The consent screen will say "The app wants to access your email, name, and profile picture" — no scary unverified-app block screen.

If someone ever wants to add scopes like Drive or Calendar, Google will require full app verification before external users can use it. Keep the scopes minimal.

### Redirect URI: `127.0.0.1`, not `localhost`

Google deprecated `http://localhost` as a loopback redirect target for OAuth in 2022. Use `http://127.0.0.1:{port}` with a random port. `google-auth-oauthlib`'s `run_local_server()` does this correctly by default — just be explicit in the flow configuration.

## Risks of a public client ID

The client ID will be in the open-source package. That's fine if we know the shape of the risk.

| Risk | Why it's manageable |
|---|---|
| **Impersonation** — anyone can build a tool using our client ID | The consent screen always shows the app name / logo configured in Ragnerock's Google Cloud Console. A user looking at the consent screen sees Ragnerock's branding regardless of which tool is performing the flow. |
| **Shared rate limit** — Google rate-limits per client ID | Request an appropriate quota on the Google project. Monitor for abuse spikes. |
| **Credential leakage** — client ID shows up in logs | Not a secret. No real impact. |
| **Compromise of the Google project** (e.g. someone publishes a rogue SDK release) | Release a new SDK version with a rotated client ID. Users can patch via `RAGNEROCK_GOOGLE_CLIENT_ID` env var without waiting for a release. |

## Ops checklist (required before shipping Google auth)

- [ ] Create a dedicated Google Cloud project for Ragnerock SDK auth (smaller blast radius than reusing a project).
- [ ] Enable the "Google Identity Services" / OAuth consent screen in that project.
- [ ] Configure the OAuth consent screen:
  - App name: "Ragnerock" (or similar)
  - User support email
  - App logo
  - Homepage URL
  - Privacy policy URL
  - Terms of service URL
  - Authorized domains
- [ ] Create an OAuth 2.0 Client ID, type "Desktop app".
- [ ] Request scopes: `openid`, `email`, `profile` (non-sensitive — no app verification needed).
- [ ] Publish the consent screen (move from "Testing" to "In production") so users outside the test-user allowlist can sign in.
- [ ] Request appropriate quotas if launch volume may exceed defaults.
- [ ] Hand the client ID to the SDK team.
- [ ] Update `ragnerock/_google_oauth.py::DEFAULT_CLIENT_ID` and ship an SDK release.

## Tests

Mirroring the existing test suite shape (`pytest-httpx`):

- `tests/test_engine_google.py`
  - **Browser flow happy path.** Mock `InstalledAppFlow.run_local_server` to return a `Credentials` stub with a known `id_token`. Assert the SDK posts that `id_token` to `POST /api/auth/google` and stores the returned `access_token`.
  - **Paste flow happy path.** Patch `builtins.input` to return a known URL; mock Google's token endpoint to return a known `id_token`; assert the SDK posts it to `/api/auth/google`.
  - **Direct credential.** Pass `credential="<jwt>"`, assert the SDK skips Google and just POSTs to `/api/auth/google`.
  - **Env-var client ID override.** Set `RAGNEROCK_GOOGLE_CLIENT_ID`; assert the flow uses it instead of the default.
  - **Failure paths.** Google token endpoint returns 400 → `AuthenticationError`. Ragnerock `/api/auth/google` returns 401 → `AuthenticationError`.

Add a `tests/conftest.py` fixture that stubs `google-auth-oauthlib` so we don't depend on the real library being installed in CI.

## Out of scope (for now)

- **Device code flow.** We could add it later for use on headless machines where `input()`-based paste is awkward (e.g. Docker containers, CI). Not needed for v1.
- **Refresh tokens.** Ragnerock's bearer tokens don't currently refresh. If that changes, re-evaluate.
- **Token caching on disk.** The SDK does not persist tokens — each new `Engine` re-auths. A future feature could cache tokens in `~/.config/ragnerock/` keyed by host+email.
