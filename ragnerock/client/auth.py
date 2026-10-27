"""Authentication endpoints (``/api/auth/...``)."""

from __future__ import annotations


from ragnerock.client._base import _ApiModel, _Section
from ragnerock.errors import raise_for_status


class AuthTokenResponse(_ApiModel):
    """Response payload for the login endpoint, carrying a bearer token."""

    access_token: str
    token_type: str = "bearer"


class _AuthSection(_Section):
    """Authentication endpoints."""

    def login(self, *, email: str, password: str) -> AuthTokenResponse:
        """Exchange email/password for a bearer token and attach it.

        Calls ``POST /api/auth/login`` with a form-urlencoded body. On
        success, the returned access token is stored on the parent client, so
        subsequent requests authenticate automatically.

        Args:
            email (str): Account email.
            password (str): Account password.

        Returns:
            AuthTokenResponse: The token response. The token is also set on the client.

        Raises:
            AuthenticationError: If the credentials are rejected.
        """
        response = self._parent._client.post(
            "/api/auth/login",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code >= 400:
            raise_for_status(response.status_code, response.text)
        model = AuthTokenResponse.model_validate(response.json())
        self._parent.auth_token = model.access_token
        return model
