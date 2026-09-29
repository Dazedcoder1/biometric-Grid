"""
Envelope encryption for credential payloads. Phase 4.

    KEK (in the KMS, never exported)
      └── DEK, 32 random bytes, ONE per credential version
            └── ciphertext, AES-256-GCM

Library choices, since the spec asks for them:

- **`cryptography`'s `AESGCM`** for the data key. It wraps OpenSSL, is the
  most widely reviewed Python crypto library, and `AESGCM` is a misuse-
  resistant one-shot API — no streaming, no update/finalize, nothing to get
  wrong. Already a dependency via python-jose.

- **AES-256-GCM over XChaCha20-Poly1305.** GCM's sharp edge is nonce reuse:
  repeat a (key, nonce) pair and you lose confidentiality and the auth key.
  Here each DEK encrypts exactly one plaintext exactly once, so there is no
  second encryption to collide with — the risk is removed structurally rather
  than by discipline. AES-256-GCM is also KMS-native, hardware-accelerated via
  AES-NI, and FIPS-validated. XChaCha20 would be right if one key covered many
  messages; it does not.

- **`os.urandom`** for DEKs and nonces — the OS CSPRNG, not `random`.

- **boto3** for real KMS, already present.

No custom cryptography: every primitive comes from a vetted library, and this
module only composes them.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

DEK_BYTES = 32   # AES-256
NONCE_BYTES = 12  # 96 bits, the GCM-recommended size
ALGORITHM = "AES-256-GCM"


class EncryptionError(RuntimeError):
    """Encryption or decryption failed. Never carries plaintext."""


class TamperDetected(EncryptionError):
    """
    The AEAD tag did not verify.

    Distinct from a general failure because it means something specific: the
    ciphertext, nonce or bound context was modified. That is a security event
    worth alerting on, not a bug to retry.
    """


@dataclass(frozen=True)
class Envelope:
    """What gets stored. Deliberately mirrors the encrypted_payloads table."""

    ciphertext: bytes
    nonce: bytes
    wrapped_dek: bytes
    kek_id: str
    alg: str = ALGORITHM

    def __repr__(self) -> str:  # pragma: no cover
        # Never let a debugger, log line or traceback print key material.
        return f"<Envelope {len(self.ciphertext)}B kek={self.kek_id} alg={self.alg}>"


# ─────────────────────────────────────────────────────────────────────────────
# Key management backends
# ─────────────────────────────────────────────────────────────────────────────


class KeyManager:
    """Wrap and unwrap data keys. The KEK never leaves the implementation."""

    key_id: str

    def wrap(self, dek: bytes) -> bytes:
        raise NotImplementedError

    def unwrap(self, wrapped: bytes) -> bytes:
        raise NotImplementedError


class MockKeyManager(KeyManager):
    """
    Local development. Holds the KEK in process memory, from KMS_MOCK_KEY.

    This is NOT the production design and must never be used with real
    credentials: the KEK sits in the same .env as the database URL, so one file
    read is total compromise. It exists so development needs no AWS account —
    and because it implements the same interface, swapping to real KMS is a
    config change, not a code change.
    """

    def __init__(self, key_id: str, raw_key: str) -> None:
        if not raw_key:
            raise EncryptionError(
                "KMS_MOCK_KEY is not set. Generate one with:\n"
                '  python -c "import base64,os; '
                'print(base64.urlsafe_b64encode(os.urandom(32)).decode())"'
            )
        try:
            self._kek = base64.urlsafe_b64decode(raw_key)
        except Exception as exc:
            raise EncryptionError("KMS_MOCK_KEY is not valid base64.") from exc

        if len(self._kek) != 32:
            raise EncryptionError(
                f"KMS_MOCK_KEY decodes to {len(self._kek)} bytes; 32 are required."
            )
        self.key_id = key_id

    def wrap(self, dek: bytes) -> bytes:
        # The KEK encrypts only short, random DEKs, and gets a fresh random
        # nonce each time. At 96 bits the collision risk is negligible at any
        # credential count this system will ever see.
        nonce = os.urandom(NONCE_BYTES)
        blob = AESGCM(self._kek).encrypt(nonce, dek, b"dek-wrap")
        return nonce + blob

    def unwrap(self, wrapped: bytes) -> bytes:
        if len(wrapped) <= NONCE_BYTES:
            raise EncryptionError("Wrapped key is truncated.")
        nonce, blob = wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:]
        try:
            return AESGCM(self._kek).decrypt(nonce, blob, b"dek-wrap")
        except InvalidTag as exc:
            raise EncryptionError(
                "Could not unwrap the data key — wrong KEK, or the stored key "
                "was modified."
            ) from exc


class AwsKeyManager(KeyManager):
    """
    Production. The KEK lives in AWS KMS and is never exported: wrap and unwrap
    are API calls, so every decryption is logged and rate-limited by AWS.

    That is the whole point of the envelope design. An attacker with the
    database gets ciphertext and wrapped keys; turning those into plaintext
    means calling KMS with our IAM role, which leaves a trail.
    """

    def __init__(self, key_id: str, region: str) -> None:
        import boto3  # imported lazily so development needs no AWS config

        self._client = boto3.client("kms", region_name=region)
        self.key_id = key_id

    def wrap(self, dek: bytes) -> bytes:
        return self._client.encrypt(KeyId=self.key_id, Plaintext=dek)["CiphertextBlob"]

    def unwrap(self, wrapped: bytes) -> bytes:
        # KeyId is passed explicitly so KMS verifies the blob belongs to the
        # key we expect, rather than decrypting with whatever key it was made
        # with — which would let a swapped blob decrypt successfully.
        return self._client.decrypt(CiphertextBlob=wrapped, KeyId=self.key_id)["Plaintext"]


_manager: KeyManager | None = None


def key_manager() -> KeyManager:
    """The configured backend, created once."""
    global _manager
    if _manager is None:
        provider = (settings.KMS_PROVIDER or "mock").lower()
        if provider == "aws":
            _manager = AwsKeyManager(settings.KMS_KEY_ID, settings.AWS_REGION)
        elif provider == "mock":
            _manager = MockKeyManager(settings.KMS_KEY_ID, settings.KMS_MOCK_KEY)
        else:
            raise EncryptionError(
                f"Unknown KMS_PROVIDER {provider!r}. Use 'mock' or 'aws'."
            )
    return _manager


def reset_key_manager() -> None:
    """Drop the cached backend. For tests and after a config change."""
    global _manager
    _manager = None


# ─────────────────────────────────────────────────────────────────────────────
# Encrypt / decrypt
# ─────────────────────────────────────────────────────────────────────────────


def build_aad(tenant_id: int, credential_id: int, version: int) -> bytes:
    """
    Additional authenticated data: not encrypted, but covered by the auth tag.

    This binds ciphertext to its row. Without it, somebody with database write
    access could move a low-value credential's ciphertext onto a high-value
    record and have it decrypt cleanly. With it, the tag fails and the read
    raises TamperDetected.
    """
    return f"v1|tenant={tenant_id}|cred={credential_id}|ver={version}".encode()


def encrypt(plaintext: str, *, aad: bytes) -> Envelope:
    """Encrypt one secret under a fresh DEK. The DEK is used exactly once."""
    if plaintext is None:
        raise EncryptionError("Nothing to encrypt.")

    km = key_manager()
    dek = os.urandom(DEK_BYTES)
    nonce = os.urandom(NONCE_BYTES)

    try:
        ciphertext = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), aad)
        wrapped = km.wrap(dek)
    finally:
        dek = _zero(dek)

    return Envelope(
        ciphertext=ciphertext, nonce=nonce, wrapped_dek=wrapped, kek_id=km.key_id
    )


def decrypt(envelope: Envelope, *, aad: bytes) -> str:
    """
    Recover the plaintext.

    Raises TamperDetected if the tag fails — wrong AAD, modified ciphertext or
    modified nonce are indistinguishable by design, and all three mean the
    stored data no longer matches what was written.
    """
    km = key_manager()

    if envelope.alg != ALGORITHM:
        raise EncryptionError(
            f"Payload uses {envelope.alg}, this build only handles {ALGORITHM}."
        )

    dek = km.unwrap(envelope.wrapped_dek)
    try:
        plaintext = AESGCM(dek).decrypt(envelope.nonce, envelope.ciphertext, aad)
    except InvalidTag as exc:
        raise TamperDetected(
            "Authentication failed: the stored payload, its nonce, or the "
            "record it is bound to has been modified."
        ) from exc
    finally:
        dek = _zero(dek)

    return plaintext.decode("utf-8")


def _zero(buf: bytes) -> bytes:
    """
    Best-effort overwrite of key material.

    Stated plainly: in CPython this cannot be guaranteed. `bytes` is immutable,
    the garbage collector may already have copied it, and freed pages are not
    zeroed. Converting to bytearray and overwriting helps marginally and costs
    nothing. Anyone needing real guarantees needs decryption in a process that
    can lock and wipe memory — out of scope, and recorded here so nobody
    assumes a guarantee that was never offered. SECURITY.md §3.5.
    """
    try:
        mutable = bytearray(buf)
        for i in range(len(mutable)):
            mutable[i] = 0
        del mutable
    except Exception:  # pragma: no cover - never let hygiene break a request
        pass
    return b""
