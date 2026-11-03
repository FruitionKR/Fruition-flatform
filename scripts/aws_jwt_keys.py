#!/usr/bin/env python3
"""Stage an RSA signing key without printing it or putting it in Terraform state.

Staging preserves a previous public key for verification. Deploy verification consumers
before changing the signing consumer. Retiring an HMAC secret is a separate action after
all consumers have moved to RSA; this command does not deploy applications.
"""
import argparse
from datetime import datetime, timezone
import subprocess
import uuid

from aws_secret_tools import read_secret, promote_secret


def rsa_pair():
    private = subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:3072"],
                             capture_output=True, check=True).stdout.decode()
    public = subprocess.run(["openssl", "pkey", "-pubout"], input=private,
                            text=True, capture_output=True, check=True).stdout
    return private, public


def stage(data, *, rotate=False):
    present = [bool(data.get(k)) for k in ("JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY", "JWT_KEY_ID")]
    if any(present) and not all(present):
        raise ValueError("Incomplete current RSA key material; reconcile before staging")
    if all(present) and not rotate:
        return False
    if rotate and data.get("JWT_PREVIOUS_PUBLIC_KEY"):
        raise ValueError("Previous verification key must be explicitly retired before another rotation")
    private, public = rsa_pair()
    data["JWT_PREVIOUS_PUBLIC_KEY"] = data.get("JWT_PUBLIC_KEY", "")
    data["JWT_PREVIOUS_KEY_ID"] = data.get("JWT_KEY_ID", "")
    data["JWT_PRIVATE_KEY"] = private
    data["JWT_PUBLIC_KEY"] = public
    data["JWT_KEY_ID"] = "jwt-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:12]
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stage", "rotate", "retire-hmac", "retire-previous"])
    parser.add_argument("--region", default="ap-northeast-2")
    parser.add_argument("--secret-id", default="fruition/app")
    parser.add_argument("--consumers-verified", action="store_true",
                        help="Required for retirement, after verifying every consumer and token transition window")
    args = parser.parse_args()
    version, data = read_secret(args.region, args.secret_id)
    if args.action in {"stage", "rotate"}:
        changed = stage(data, rotate=args.action == "rotate")
    else:
        if not args.consumers_verified or not all(data.get(k) for k in ("JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY", "JWT_KEY_ID")):
            raise ValueError("Retirement requires verified RSA consumers")
        if args.action == "retire-hmac":
            changed = "JWT_SECRET" in data
            data.pop("JWT_SECRET", None)
        else:
            changed = bool(data.get("JWT_PREVIOUS_PUBLIC_KEY"))
            data["JWT_PREVIOUS_PUBLIC_KEY"] = ""
            data["JWT_PREVIOUS_KEY_ID"] = ""
    if changed:
        promote_secret(args.region, args.secret_id, version, data)
    print("JWT key metadata updated" if changed else "No key change needed")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, subprocess.CalledProcessError):
        raise SystemExit("JWT key operation failed; secret values and provider errors suppressed") from None
