#!/usr/bin/env python3
"""Copy only the frontend access code to the WAF-only Secret, without printing it.

Run after changing ACCESS_CODE and before Terraform plans WAF. Bootstrap the
destination Secret using Terraform first. This does not change frontend values.
"""
import argparse

from aws_secret_tools import read_secret, promote_secret


def sync(region, source, destination):
    source_version, source_data = read_secret(region, source)
    destination_version, destination_data = read_secret(region, destination)
    # Also catches aliases pointing at the same Secret, without ever overwriting it.
    if set(destination_data) != {"ACCESS_CODE"}:
        raise ValueError("Destination must contain ACCESS_CODE only")
    code = source_data.get("ACCESS_CODE")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Source access code must be a nonempty string")
    # Preserve the original bytes. Both frontend and WAF apply their own trim.
    changed = destination_data["ACCESS_CODE"] != code
    if changed:
        promote_secret(region, destination, destination_version, {"ACCESS_CODE": code})
    current_source, _ = read_secret(region, source)
    if current_source != source_version:
        raise RuntimeError("Source version changed during copy; reconcile before Terraform apply")
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", default="ap-northeast-2")
    parser.add_argument("--source-secret", default="fruition/app")
    parser.add_argument("--destination-secret", default="fruition/waf-access-code")
    args = parser.parse_args()
    if args.source_secret == args.destination_secret:
        raise ValueError("Source and destination must differ")
    changed = sync(args.region, args.source_secret, args.destination_secret)
    print("WAF-only access code synchronized" if changed else "WAF-only access code already synchronized")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError, KeyError):
        raise SystemExit("Access code copy failed; values and provider errors suppressed") from None
