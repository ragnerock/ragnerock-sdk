"""Client-side transport sealing for GitOps secret values.

Before a ``Secret`` is uploaded, each resolved value is encrypted to a public
key that only the target instance can open, so the request body carries no
recoverable plaintext. A fresh Fernet data key encrypts the value and is
wrapped with RSA-OAEP (SHA-256) under the instance key — hybrid encryption is
required, since RSA alone cannot wrap a service-account JSON or a PEM. The
serialized form is four dot-delimited fields::

    rgnk-sealed.v1.<base64url(wrapped_dek)>.<fernet_token>

The instance publishes its key at ``GET /api/gitops/sealing-key``. Pinning the
key instead of fetching it (``sealing_public_key=``) also protects against an
intermediary that terminates TLS.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from ragnerock.errors import GitOpsError

SEALED_PREFIX = "rgnk-sealed"
"""First field of every sealed value."""

SEALED_VERSION = "v1"
"""Format version carried in the second field of every sealed value."""

_FINGERPRINT_PREFIX = "sha256:"


class SealingError(GitOpsError):
    """Raised when a sealing key cannot be loaded or a value cannot be sealed."""


def _oaep() -> padding.OAEP:
    """Return the OAEP padding configuration used for data-key wrapping.

    Returns:
        padding.OAEP: SHA-256 for both the digest and the MGF1 mask.
    """
    return padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(),
        label=None,
    )


def load_public_key(pem: str) -> rsa.RSAPublicKey:
    """Load a PEM-encoded sealing public key.

    Args:
        pem (str): PEM-encoded SubjectPublicKeyInfo.

    Returns:
        rsa.RSAPublicKey: The parsed key.

    Raises:
        SealingError: If the PEM is malformed or not an RSA key.
    """
    try:
        key = serialization.load_pem_public_key(pem.encode())
    except (ValueError, TypeError, UnsupportedAlgorithm) as e:
        raise SealingError(f"could not parse sealing public key: {e}") from e
    if not isinstance(key, rsa.RSAPublicKey):
        raise SealingError(f"sealing public key must be RSA, got {type(key).__name__}")
    return key


def key_fingerprint(public_key: rsa.RSAPublicKey) -> str:
    """Return a stable fingerprint for a sealing public key.

    SHA-256 over the DER SubjectPublicKeyInfo, so the value is independent of
    PEM whitespace and matches what the instance reports for the same key.

    Args:
        public_key (rsa.RSAPublicKey): The key to fingerprint.

    Returns:
        str: ``sha256:<hex>``.
    """
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return f"{_FINGERPRINT_PREFIX}{hashlib.sha256(der).hexdigest()}"


def is_sealed(value: str) -> bool:
    """Report whether a string looks like a sealed value.

    Args:
        value (str): The candidate string.

    Returns:
        bool: ``True`` if it carries the ``rgnk-sealed.v1.`` prefix.
    """
    return value.startswith(f"{SEALED_PREFIX}.{SEALED_VERSION}.")


def seal(plaintext: str, public_key: rsa.RSAPublicKey) -> str:
    """Seal a plaintext value to an instance's sealing public key.

    Args:
        plaintext (str): The secret value.
        public_key (rsa.RSAPublicKey): The instance's sealing key.

    Returns:
        str: The serialized sealed value.

    Raises:
        SealingError: If the key is too small to wrap a data key under OAEP.
    """
    dek = Fernet.generate_key()
    token = Fernet(dek).encrypt(plaintext.encode()).decode()
    try:
        wrapped = public_key.encrypt(dek, _oaep())
    except ValueError as e:
        raise SealingError(f"could not wrap the data key: {e}") from e
    encoded = base64.urlsafe_b64encode(wrapped).decode()
    return f"{SEALED_PREFIX}.{SEALED_VERSION}.{encoded}.{token}"
