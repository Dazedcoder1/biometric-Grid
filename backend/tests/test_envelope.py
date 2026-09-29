"""
Envelope encryption: round-trip, tamper detection, wrong key, key versioning.

Every test drives the real AESGCM implementation — there is no mocking of the
crypto itself, only of key custody.
"""

from __future__ import annotations

import base64
import os

import pytest

from app.core import envelope as env


@pytest.fixture(autouse=True)
def mock_kms(monkeypatch):
    """A deterministic local KEK, isolated per test."""
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setattr(env.settings, "KMS_PROVIDER", "mock", raising=False)
    monkeypatch.setattr(env.settings, "KMS_MOCK_KEY", key, raising=False)
    monkeypatch.setattr(env.settings, "KMS_KEY_ID", "test-kek-v1", raising=False)
    env.reset_key_manager()
    yield
    env.reset_key_manager()


AAD = env.build_aad(tenant_id=1, credential_id=42, version=1)


# ─── round trip ──────────────────────────────────────────────────────────────

def test_round_trip():
    blob = env.encrypt("correct horse battery staple", aad=AAD)
    assert env.decrypt(blob, aad=AAD) == "correct horse battery staple"


def test_round_trip_unicode_and_long_values():
    for secret in ("pässwörd-✓-🔐", "x" * 10_000, " ", "0"):
        blob = env.encrypt(secret, aad=AAD)
        assert env.decrypt(blob, aad=AAD) == secret


def test_ciphertext_does_not_contain_the_plaintext():
    secret = "hunter2-unmistakable-marker"
    blob = env.encrypt(secret, aad=AAD)
    assert secret.encode() not in blob.ciphertext
    assert secret.encode() not in blob.wrapped_dek


def test_same_plaintext_encrypts_differently_every_time():
    """Fresh DEK and nonce per call, so identical secrets are not correlatable."""
    a = env.encrypt("same", aad=AAD)
    b = env.encrypt("same", aad=AAD)
    assert a.ciphertext != b.ciphertext
    assert a.nonce != b.nonce
    assert a.wrapped_dek != b.wrapped_dek


def test_envelope_repr_leaks_nothing():
    blob = env.encrypt("top-secret-value", aad=AAD)
    text = repr(blob)
    assert "top-secret-value" not in text
    assert str(blob.wrapped_dek) not in text


# ─── tamper detection ────────────────────────────────────────────────────────

def test_modified_ciphertext_is_detected():
    blob = env.encrypt("original", aad=AAD)
    broken = bytearray(blob.ciphertext)
    broken[0] ^= 0x01                      # one bit
    tampered = env.Envelope(bytes(broken), blob.nonce, blob.wrapped_dek, blob.kek_id)

    with pytest.raises(env.TamperDetected):
        env.decrypt(tampered, aad=AAD)


def test_modified_nonce_is_detected():
    blob = env.encrypt("original", aad=AAD)
    broken = bytearray(blob.nonce)
    broken[0] ^= 0x01
    tampered = env.Envelope(blob.ciphertext, bytes(broken), blob.wrapped_dek, blob.kek_id)

    with pytest.raises(env.TamperDetected):
        env.decrypt(tampered, aad=AAD)


def test_truncated_ciphertext_is_detected():
    blob = env.encrypt("original", aad=AAD)
    tampered = env.Envelope(blob.ciphertext[:-1], blob.nonce, blob.wrapped_dek, blob.kek_id)

    with pytest.raises(env.TamperDetected):
        env.decrypt(tampered, aad=AAD)


def test_wrong_aad_is_rejected():
    """The attack this prevents: moving ciphertext between records.

    Someone with database write access copies a low-value credential's
    ciphertext onto a high-value row. Without AAD binding it decrypts cleanly.
    """
    blob = env.encrypt("secret for credential 42", aad=AAD)
    other_row = env.build_aad(tenant_id=1, credential_id=99, version=1)

    with pytest.raises(env.TamperDetected):
        env.decrypt(blob, aad=other_row)


def test_wrong_tenant_in_aad_is_rejected():
    blob = env.encrypt("tenant 1 secret", aad=AAD)
    other_tenant = env.build_aad(tenant_id=2, credential_id=42, version=1)

    with pytest.raises(env.TamperDetected):
        env.decrypt(blob, aad=other_tenant)


def test_wrong_version_in_aad_is_rejected():
    blob = env.encrypt("version 1 secret", aad=AAD)
    other_version = env.build_aad(tenant_id=1, credential_id=42, version=2)

    with pytest.raises(env.TamperDetected):
        env.decrypt(blob, aad=other_version)


# ─── key handling ────────────────────────────────────────────────────────────

def test_wrong_kek_cannot_unwrap(monkeypatch):
    """A database leak without the KEK yields nothing."""
    blob = env.encrypt("secret", aad=AAD)

    monkeypatch.setattr(
        env.settings, "KMS_MOCK_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode(),
        raising=False,
    )
    env.reset_key_manager()

    with pytest.raises(env.EncryptionError):
        env.decrypt(blob, aad=AAD)


def test_corrupted_wrapped_dek_is_detected():
    blob = env.encrypt("secret", aad=AAD)
    broken = bytearray(blob.wrapped_dek)
    broken[-1] ^= 0x01
    tampered = env.Envelope(blob.ciphertext, blob.nonce, bytes(broken), blob.kek_id)

    with pytest.raises(env.EncryptionError):
        env.decrypt(tampered, aad=AAD)


def test_truncated_wrapped_dek_is_rejected():
    blob = env.encrypt("secret", aad=AAD)
    tampered = env.Envelope(blob.ciphertext, blob.nonce, b"short", blob.kek_id)

    with pytest.raises(env.EncryptionError):
        env.decrypt(tampered, aad=AAD)


def test_kek_id_is_recorded_for_rotation():
    """Re-encryption finds outstanding work by kek_id, not by a job's memory."""
    blob = env.encrypt("secret", aad=AAD)
    assert blob.kek_id == "test-kek-v1"
    assert blob.alg == "AES-256-GCM"


def test_unknown_algorithm_is_refused():
    blob = env.encrypt("secret", aad=AAD)
    future = env.Envelope(
        blob.ciphertext, blob.nonce, blob.wrapped_dek, blob.kek_id, alg="AES-512-FUTURE"
    )
    with pytest.raises(env.EncryptionError, match="only handles"):
        env.decrypt(future, aad=AAD)


def test_missing_mock_key_fails_clearly(monkeypatch):
    monkeypatch.setattr(env.settings, "KMS_MOCK_KEY", "", raising=False)
    env.reset_key_manager()
    with pytest.raises(env.EncryptionError, match="KMS_MOCK_KEY"):
        env.encrypt("secret", aad=AAD)


def test_wrong_length_mock_key_fails_clearly(monkeypatch):
    monkeypatch.setattr(
        env.settings, "KMS_MOCK_KEY",
        base64.urlsafe_b64encode(os.urandom(16)).decode(),
        raising=False,
    )
    env.reset_key_manager()
    with pytest.raises(env.EncryptionError, match="32"):
        env.encrypt("secret", aad=AAD)


def test_unknown_provider_fails_clearly(monkeypatch):
    monkeypatch.setattr(env.settings, "KMS_PROVIDER", "azure", raising=False)
    env.reset_key_manager()
    with pytest.raises(env.EncryptionError, match="KMS_PROVIDER"):
        env.encrypt("secret", aad=AAD)


# ─── primitives ──────────────────────────────────────────────────────────────

def test_nonce_and_dek_sizes():
    blob = env.encrypt("secret", aad=AAD)
    assert len(blob.nonce) == 12       # 96 bits, GCM recommended
    assert env.DEK_BYTES == 32         # AES-256


def test_aad_is_stable_and_distinct():
    assert env.build_aad(1, 2, 3) == env.build_aad(1, 2, 3)
    assert env.build_aad(1, 2, 3) != env.build_aad(1, 2, 4)
    assert env.build_aad(1, 2, 3) != env.build_aad(2, 1, 3)
