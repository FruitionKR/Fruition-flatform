#!/usr/bin/env python3
"""Prepare or apply GitHub feedback approval/main-only protection without secrets."""
import argparse
import json
import subprocess

REPO = "FruitionKR/Fruition-flatform"
BASE = f"repos/{REPO}/environments/feedback"


def api(path, method="GET", body=None):
    args = ["gh", "api", path, "--method", method]
    if body is not None:
        args += ["--input", "-"]
    response = subprocess.run(args, input=None if body is None else json.dumps(body),
                              text=True, capture_output=True, check=True)
    return json.loads(response.stdout) if response.stdout else {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewer", required=True, help="승인 담당 GitHub 사용자")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    user = api("users/" + args.reviewer)
    body = {"wait_timer": 0, "prevent_self_review": False, "can_admins_bypass": False,
            "reviewers": [{"type": "User", "id": user["id"]}],
            "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}}
    print(json.dumps({"repository": REPO, "environment": "feedback", "reviewer": user["login"],
                      "branch": "main", "self_approval": True, "admin_bypass": False}, ensure_ascii=False))
    if not args.apply:
        return
    api(BASE, "PUT", body)
    policies = api(BASE + "/deployment-branch-policies")["branch_policies"]
    if any(p["name"] != "main" or p.get("type", "branch") != "branch" for p in policies):
        raise SystemExit("기존 main 이외 배포 규칙이 있습니다. 자동 삭제하지 않았습니다")
    if not policies:
        api(BASE + "/deployment-branch-policies", "POST", {"name": "main", "type": "branch"})
    api(f"repos/{REPO}/actions/permissions/fork-pr-contributor-approval", "PUT",
        {"approval_policy": "all_external_contributors"})
    actual = api(BASE)
    reviewers = [r for r in actual["protection_rules"] if r["type"] == "required_reviewers"]
    assert reviewers and any(x["reviewer"]["id"] == user["id"] for x in reviewers[0]["reviewers"])
    assert actual["deployment_branch_policy"]["custom_branch_policies"]
    assert any(p["name"] == "main" for p in api(BASE + "/deployment-branch-policies")["branch_policies"])
    assert api(f"repos/{REPO}/actions/permissions/fork-pr-contributor-approval")["approval_policy"] == "all_external_contributors"
    print("PASS: feedback 환경 승인, main 제한, 모든 외부 PR 실행 승인 확인")


if __name__ == "__main__":
    main()
