"""Cryptographic Human-in-the-Loop approval gate.

token   mode: approver proves identity with a shared token; API converts it into an HMAC attestation
              so credentials never travel over the event bus.
ed25519 mode: approver signs the canonical decision offline with their private key (recommended for
              physical interventions); API and worker both verify against registered public keys.
"""
from __future__ import annotations

import hashlib
import hmac

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization


class ApprovalError(Exception):
    """Raised when an approval decision cannot be authenticated."""


def canonical(thread_id: str, nonce: str, approve: bool, approver: str) -> bytes:
    return f"aether-approval/v1|{thread_id}|{nonce}|{int(approve)}|{approver}".encode()


class ApprovalVerifier:
    def __init__(self, mode: str, tokens: dict[str, str], pubkeys: dict[str, str], hmac_secret: str) -> None:
        if mode not in ("token", "ed25519"):
            raise ValueError("approval mode must be 'token' or 'ed25519'")
        self.mode, self._tokens, self._pubkeys, self._secret = mode, tokens, pubkeys, hmac_secret.encode()

    def _hmac(self, msg: bytes) -> str:
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()

    def _verify_ed25519(self, approver: str, msg: bytes, sig_hex: str) -> None:
        pub = self._pubkeys.get(approver)
        if not pub:
            raise ApprovalError("unknown approver")
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(pub)).verify(bytes.fromhex(sig_hex), msg)
        except (InvalidSignature, ValueError) as exc:
            raise ApprovalError("invalid signature") from exc

    def authenticate(self, thread_id: str, nonce: str, approve: bool, approver: str,
                     token: str | None, signature: str | None) -> str:
        """API side. Returns an attestation string safe to forward on the bus."""
        msg = canonical(thread_id, nonce, approve, approver)
        if self.mode == "token":
            expected = self._tokens.get(approver)
            if not expected or not token or not hmac.compare_digest(expected, token):
                raise ApprovalError("invalid approver credentials")
            return "hmac:" + self._hmac(msg)
        if not signature:
            raise ApprovalError("signature required")
        self._verify_ed25519(approver, msg, signature)
        return "ed25519:" + signature

    def verify_attested(self, thread_id: str, nonce: str, approve: bool, approver: str, attestation: str) -> None:
        """Worker side (defence in depth): re-verify what the API forwarded."""
        msg = canonical(thread_id, nonce, approve, approver)
        scheme, _, value = attestation.partition(":")
        if scheme == "hmac":
            if not hmac.compare_digest(self._hmac(msg), value):
                raise ApprovalError("bad attestation")
        elif scheme == "ed25519":
            self._verify_ed25519(approver, msg, value)
        else:
            raise ApprovalError("unknown attestation scheme")


def generate_approver_keypair() -> tuple[str, str]:
    """Returns (private_hex, public_hex) for ed25519 mode onboarding."""
    priv = Ed25519PrivateKey.generate()
    raw_priv = priv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    raw_pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return raw_priv.hex(), raw_pub.hex()


def sign_decision(private_hex: str, thread_id: str, nonce: str, approve: bool, approver: str) -> str:
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))
    return key.sign(canonical(thread_id, nonce, approve, approver)).hex()
