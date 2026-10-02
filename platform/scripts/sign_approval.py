#!/usr/bin/env python3
"""ed25519 approver tooling (APPROVAL_MODE=ed25519).

  keygen                                   → prints private + public hex (register the PUBLIC key in APPROVER_PUBKEYS=name:<hex>)
  sign <priv_hex> <thread_id> <nonce> <approve|reject> <approver>  → prints signature to POST as {"signature": ...}
"""
import sys

from security.approvals import generate_approver_keypair, sign_decision

if len(sys.argv) >= 2 and sys.argv[1] == "keygen":
    priv, pub = generate_approver_keypair()
    print(f"PRIVATE (keep offline/HSM): {priv}\nPUBLIC  (APPROVER_PUBKEYS=name:{pub})")
elif len(sys.argv) == 7 and sys.argv[1] == "sign":
    _, _, priv, thread, nonce, decision, approver = sys.argv
    print(sign_decision(priv, thread, nonce, decision == "approve", approver))
else:
    sys.exit(__doc__)
