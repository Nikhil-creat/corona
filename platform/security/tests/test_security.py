import pytest

from security.approvals import ApprovalError, ApprovalVerifier, generate_approver_keypair, sign_decision
from security.pq import generate_recipient_keys, open_envelope, seal, PublicBundle


def test_envelope_roundtrip_and_tamper():
    keys = generate_recipient_keys()
    env = seal(PublicBundle.from_json(keys.public.to_json()), b"telemetry", aad=b"N-01")
    assert open_envelope(keys, env, aad=b"N-01") == b"telemetry"
    with pytest.raises(Exception):
        open_envelope(keys, env, aad=b"N-02")


def test_token_approval_and_attestation():
    v = ApprovalVerifier("token", {"ops": "s3cret"}, {}, "h" * 32)
    att = v.authenticate("t1", "n1", True, "ops", "s3cret", None)
    v.verify_attested("t1", "n1", True, "ops", att)
    with pytest.raises(ApprovalError):
        v.verify_attested("t1", "n1", False, "ops", att)  # decision flipped → attestation invalid
    with pytest.raises(ApprovalError):
        v.authenticate("t1", "n1", True, "ops", "wrong", None)


def test_ed25519_approval():
    priv, pub = generate_approver_keypair()
    v = ApprovalVerifier("ed25519", {}, {"ops": pub}, "h" * 32)
    sig = sign_decision(priv, "t1", "n1", True, "ops")
    att = v.authenticate("t1", "n1", True, "ops", None, sig)
    v.verify_attested("t1", "n1", True, "ops", att)
    with pytest.raises(ApprovalError):
        v.authenticate("t1", "n1", False, "ops", None, sig)
