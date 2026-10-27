"""Tests for the client side of the transport seal (:mod:`ragnerock.gitops.sealing`).

The seal format carries no version negotiation, so a change here that the
server can't open is a silent correctness bug. These tests pin the format.
"""

from __future__ import annotations

import base64
from collections.abc import Callable

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from ragnerock.gitops import (
    SealingError,
    is_sealed,
    key_fingerprint,
    load_public_key,
    seal,
)
from ragnerock.gitops.sealing import SEALED_PREFIX, SEALED_VERSION


def test_format_tokens_are_pinned() -> None:
    assert SEALED_PREFIX == "rgnk-sealed"
    assert SEALED_VERSION == "v1"


def test_sealed_value_has_four_fields(sealing_key: rsa.RSAPrivateKey) -> None:
    blob = seal("hello", sealing_key.public_key())
    prefix, version, wrapped, token = blob.split(".", 3)
    assert (prefix, version) == ("rgnk-sealed", "v1")
    # The wrapped data key is one RSA block.
    assert len(base64.urlsafe_b64decode(wrapped)) == sealing_key.key_size // 8
    assert "." not in token
    assert is_sealed(blob)


def test_round_trip(
    sealing_key: rsa.RSAPrivateKey, unseal: Callable[[str], str]
) -> None:
    value = '{"type": "service_account", "private_key": "-----BEGIN..."}\nline 2'
    assert unseal(seal(value, sealing_key.public_key())) == value


def test_each_seal_uses_a_fresh_data_key(sealing_key: rsa.RSAPrivateKey) -> None:
    public_key = sealing_key.public_key()
    assert seal("same", public_key) != seal("same", public_key)


def test_plaintext_does_not_appear_in_the_blob(sealing_key: rsa.RSAPrivateKey) -> None:
    assert "very-secret" not in seal("very-secret", sealing_key.public_key())


def test_load_public_key_round_trips(sealing_pem: str) -> None:
    assert isinstance(load_public_key(sealing_pem), rsa.RSAPublicKey)


def test_load_public_key_rejects_garbage() -> None:
    with pytest.raises(SealingError, match="could not parse"):
        load_public_key("not a pem")


def test_load_public_key_rejects_non_rsa_keys() -> None:
    pem = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    with pytest.raises(SealingError, match="must be RSA"):
        load_public_key(pem)


def test_fingerprint_ignores_pem_whitespace(sealing_pem: str) -> None:
    reflowed = "\n" + sealing_pem.replace("\n", "\r\n") + "\n\n"
    assert key_fingerprint(load_public_key(sealing_pem)) == key_fingerprint(
        load_public_key(reflowed)
    )


def test_fingerprint_shape(sealing_pem: str) -> None:
    fingerprint = key_fingerprint(load_public_key(sealing_pem))
    assert fingerprint.startswith("sha256:")
    assert len(fingerprint) == len("sha256:") + 64


def test_is_sealed_rejects_plain_values() -> None:
    assert not is_sealed("plaintext")
    assert not is_sealed("rgnk-sealed.v2.x.y")
