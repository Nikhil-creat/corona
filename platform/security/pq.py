"""Hybrid post-quantum envelope encryption for edge→cloud telemetry.

KEM:   X25519  +  ML-KEM-768 (via liboqs-python, when installed)  → combined with HKDF-SHA256
AEAD:  AES-256-GCM

Hybrid construction: the session key is secure if EITHER X25519 OR ML-KEM holds.
If liboqs is not present the envelope degrades to X25519-only and is labelled `pq=false`;
set PQ_REQUIRED=true (or pq_required=True) to refuse that downgrade.
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

try:  # optional native dependency
    import oqs  # type: ignore

    _PQ_ALG = next((a for a in ("ML-KEM-768", "Kyber768") if a in oqs.get_enabled_kem_mechanisms()), None)
except Exception:  # pragma: no cover - depends on environment
    oqs = None
    _PQ_ALG = None

PQ_AVAILABLE = _PQ_ALG is not None
_INFO = b"corona/v1/session"


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode())


@dataclass(frozen=True)
class PublicBundle:
    x25519: bytes
    pq: bytes | None
    alg: str | None

    def to_json(self) -> str:
        return json.dumps({"x25519": _b64(self.x25519), "pq": _b64(self.pq) if self.pq else None, "alg": self.alg})

    @staticmethod
    def from_json(raw: str) -> "PublicBundle":
        d = json.loads(raw)
        return PublicBundle(_unb64(d["x25519"]), _unb64(d["pq"]) if d.get("pq") else None, d.get("alg"))


@dataclass(frozen=True)
class RecipientKeys:
    x25519_private: bytes
    pq_secret: bytes | None
    public: PublicBundle


def _require_pq(pq_required: bool) -> None:
    if pq_required and not PQ_AVAILABLE:
        raise RuntimeError("PQ_REQUIRED=true but no ML-KEM backend (liboqs-python) is available")


def generate_recipient_keys(pq_required: bool = False) -> RecipientKeys:
    _require_pq(pq_required)
    xpriv = X25519PrivateKey.generate()
    xpub = xpriv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    xraw = xpriv.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pq_pub = pq_sec = None
    if PQ_AVAILABLE:
        kem = oqs.KeyEncapsulation(_PQ_ALG)
        pq_pub = kem.generate_keypair()
        pq_sec = kem.export_secret_key()
    return RecipientKeys(xraw, pq_sec, PublicBundle(xpub, pq_pub, _PQ_ALG))


def _derive(x_secret: bytes, pq_secret: bytes | None, salt: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=_INFO).derive(x_secret + (pq_secret or b""))


def seal(recipient: PublicBundle, plaintext: bytes, aad: bytes = b"", pq_required: bool = False) -> str:
    """Encrypt to a recipient's public bundle; returns a JSON envelope string."""
    _require_pq(pq_required)
    eph = X25519PrivateKey.generate()
    eph_pub = eph.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    x_secret = eph.exchange(X25519PublicKey.from_public_bytes(recipient.x25519))
    pq_ct = pq_ss = None
    if recipient.pq and PQ_AVAILABLE and recipient.alg == _PQ_ALG:
        pq_ct, pq_ss = oqs.KeyEncapsulation(_PQ_ALG).encap_secret(recipient.pq)
    elif pq_required:
        raise RuntimeError("recipient bundle has no compatible ML-KEM key")
    salt, nonce = os.urandom(16), os.urandom(12)
    ct = AESGCM(_derive(x_secret, pq_ss, salt)).encrypt(nonce, plaintext, aad)
    return json.dumps(
        {
            "v": 1,
            "pq": pq_ct is not None,
            "alg": _PQ_ALG if pq_ct else None,
            "epk": _b64(eph_pub),
            "kem_ct": _b64(pq_ct) if pq_ct else None,
            "salt": _b64(salt),
            "nonce": _b64(nonce),
            "ct": _b64(ct),
        }
    )


def open_envelope(keys: RecipientKeys, envelope: str, aad: bytes = b"") -> bytes:
    d = json.loads(envelope)
    x_secret = X25519PrivateKey.from_private_bytes(keys.x25519_private).exchange(
        X25519PublicKey.from_public_bytes(_unb64(d["epk"]))
    )
    pq_ss = None
    if d.get("pq"):
        if not (PQ_AVAILABLE and keys.pq_secret):
            raise RuntimeError("envelope requires ML-KEM but no PQ secret/backend available")
        pq_ss = oqs.KeyEncapsulation(_PQ_ALG, secret_key=keys.pq_secret).decap_secret(_unb64(d["kem_ct"]))
    return AESGCM(_derive(x_secret, pq_ss, _unb64(d["salt"]))).decrypt(_unb64(d["nonce"]), _unb64(d["ct"]), aad)
