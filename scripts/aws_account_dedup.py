"""Remove duplicate accounts that share one email across sign-up providers.

같은 이메일로 기본(local) 가입과 소셜 가입을 따로 한 사용자는 소셜 연동 시 409 OAUTH_ACCOUNT_ALREADY_LINKED가 난다.
이메일마다 직접 올린 활성 문서가 가장 많은 계정 하나만 남기고(동점이면 local, 그다음 먼저 가입한 계정) 나머지를 지운다.
지운 계정의 문서·채팅·위키는 core_db·ai_db에 고아로 남으며 옮기지 않는다(운영 결정).

access_db와 core_db는 다른 RDS라 JOIN할 수 없어 일회성 psql Pod 두 개로 따로 읽고 여기서 판단한다.
이메일은 md5 앞 10자로만 화면에 남긴다.

사용(운영 kubeconfig·AWS 자격 증명이 있는 운영자 셸):
  python3 scripts/aws_account_dedup.py report
  python3 scripts/aws_account_dedup.py apply --confirm <report가 출력한 plan hash>
apply는 계획을 다시 읽어 hash가 같을 때만 access RDS 스냅샷을 만든 뒤 한 트랜잭션으로 반영한다.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict

REGION = "ap-northeast-2"
CLUSTER = "fruition-eks"
NS = "fruition"
ACCESS_INSTANCE = "fruition-access-postgres"
# NetworkPolicy의 DB egress 허용 라벨 중 Service selector에 잡히지 않는 preflight 라벨을 쓴다.
# app=access-svc로 띄우면 access-svc Service가 psql Pod로도 요청을 보낸다.
DATABASES = {
    "access": {"deploy": "access-svc", "label": "access-db-preflight", "db": "ACCESS_DB_NAME",
               "user": "ACCESS_DB_RUNTIME_USER", "secret": "fruition-access", "password": "ACCESS_DB_RUNTIME_PASSWORD"},
    "core": {"deploy": "document-svc", "label": "document-db-preflight", "db": "CORE_DB_NAME",
             "user": "CORE_DB_RUNTIME_USER", "secret": "fruition-document", "password": "CORE_DB_RUNTIME_PASSWORD"},
}
# SQL에 값을 직접 넣으므로 DB에서 읽은 ID라도 형식을 확인한다.
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

ACCESS_REPORT_SQL = """
WITH dup AS (SELECT lower(email) AS e FROM users GROUP BY lower(email) HAVING count(*) > 1),
du AS (SELECT u.id, u.provider, u.created_at, left(md5(lower(u.email)), 10) AS k
       FROM users u JOIN dup ON lower(u.email) = dup.e),
ws AS (SELECT DISTINCT m.workspace_id FROM workspace_members m
       JOIN du ON du.id = m.user_id JOIN workspaces w ON w.id = m.workspace_id
       WHERE m.role = 'OWNER' AND w.deleted_at IS NULL)
SELECT 'U', k, id, provider, to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US') FROM du
UNION ALL
SELECT 'W', m.workspace_id, m.user_id, m.role, '' FROM workspace_members m JOIN ws USING (workspace_id)
ORDER BY 1, 2, 3
"""
# 직접 올린 활성 문서만 센다. 휴지통·스킬 참고 문서·채팅 내보내기는 제외한다. 오래된 행은 origin이 NULL이다.
CORE_COUNT_SQL = """
SELECT user_id, count(*) FROM documents
WHERE deleted_at IS NULL AND coalesce(origin, 'upload') NOT IN ('skill_reference', 'chat_export')
  AND user_id IN ({ids})
GROUP BY user_id ORDER BY 1
"""


def sql_ids(ids):
    ids = sorted(set(ids))
    for value in ids:
        if not SAFE_ID.fullmatch(value):
            raise ValueError("Unexpected id format")
    return ", ".join(f"'{value}'" for value in ids)


def parse_access(text):
    users, members = [], defaultdict(list)
    for line in filter(None, text.splitlines()):
        kind, a, b, c, d = line.split("\t")
        if kind == "U":
            users.append({"key": a, "id": b, "provider": c, "created": d})
        elif kind == "W":
            members[a].append({"user_id": b, "role": c})
        else:
            raise ValueError("Unexpected access row")
    return users, dict(members)


def parse_counts(text):
    counts = {}
    for line in filter(None, text.splitlines()):
        user_id, count = line.split("\t")
        counts[user_id] = int(count)
    return counts


def decide(users, members, counts):
    groups = defaultdict(list)
    for user in users:
        groups[user["key"]].append({**user, "docs": counts.get(user["id"], 0)})
    plan_groups, keep_of = [], {}
    for key in sorted(groups):
        ranked = sorted(groups[key], key=lambda u: (-u["docs"], u["provider"] != "local", u["created"], u["id"]))
        keep, drop = ranked[0], ranked[1:]
        plan_groups.append({"key": key,
                            "keep": {k: keep[k] for k in ("id", "provider", "docs")},
                            "delete": [{k: u[k] for k in ("id", "provider", "docs")} for u in drop]})
        keep_of.update({u["id"]: keep["id"] for u in drop})
    workspaces = []
    for workspace_id in sorted(members):
        rows = members[workspace_id]
        gone = sorted(r["user_id"] for r in rows if r["role"] == "OWNER" and r["user_id"] in keep_of)
        if not gone:
            continue
        remaining = [r for r in rows if r["user_id"] not in keep_of]
        if any(r["role"] == "OWNER" for r in remaining):
            continue
        if not remaining:
            # 지울 계정만 있던 워크스페이스는 문서와 함께 버리므로 휴지통으로 보낸다.
            workspaces.append({"id": workspace_id, "action": "trash", "user_id": gone[0]})
            continue
        # 다른 멤버가 남는 워크스페이스는 OWNER가 사라지지 않게 남는 계정을 OWNER로 둔다.
        target = keep_of[gone[0]]
        action = "promote" if any(r["user_id"] == target for r in remaining) else "add_owner"
        workspaces.append({"id": workspace_id, "action": action, "user_id": target})
    return {"groups": plan_groups, "workspaces": workspaces}


def plan_hash(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()[:16]


# Pod command에서 Kubernetes는 $$를 $로 줄인다. DO 블록은 이름 붙은 dollar quote($do$)를 쓴다.
def apply_sql(plan):
    deleted = [u["id"] for g in plan["groups"] for u in g["delete"]]
    ids = sql_ids(deleted)
    lines = [f"SELECT 1 FROM users WHERE id IN ({ids}) FOR UPDATE;",
             f"DO $do$ BEGIN IF (SELECT count(*) FROM users WHERE id IN ({ids})) <> {len(deleted)} "
             "THEN RAISE EXCEPTION 'duplicate accounts changed since report'; END IF; END $do$;"]
    for ws in plan["workspaces"]:
        wid, uid = sql_ids([ws["id"]]), sql_ids([ws["user_id"]])
        if ws["action"] == "promote":
            lines.append(f"UPDATE workspace_members SET role = 'OWNER' WHERE workspace_id = {wid} AND user_id = {uid};")
        elif ws["action"] == "add_owner":
            lines.append("INSERT INTO workspace_members (workspace_id, user_id, role, joined_at) "
                         f"VALUES ({wid}, {uid}, 'OWNER', now());")
        else:
            lines.append(f"UPDATE workspaces SET deleted_at = now(), deleted_by = {uid}, updated_at = now() "
                         f"WHERE id = {wid} AND deleted_at IS NULL;")
    # refresh token은 users FK가 없어 남는다. 남아도 refresh에서 거절되지만 같이 지운다.
    lines += [f"DELETE FROM user_refresh_tokens WHERE user_id IN ({ids});",
              f"DELETE FROM users WHERE id IN ({ids});",
              f"DO $do$ BEGIN IF EXISTS (SELECT 1 FROM users WHERE id IN ({ids})) "
              "THEN RAISE EXCEPTION 'delete incomplete'; END IF; END $do$;"]
    return "\n".join(lines)


def kubectl(*args, **kwargs):
    return subprocess.run(["kubectl", *args], check=True, text=True, capture_output=True, **kwargs).stdout


def run_sql(database, sql, single_transaction=False):
    cfg = DATABASES[database]
    host = kubectl("-n", NS, "get", "deploy", cfg["deploy"], "-o",
                   "jsonpath={.spec.template.spec.containers[0].env[?(@.name==\"POSTGRES_HOST\")].value}").strip()
    if not host:
        raise ValueError(f"POSTGRES_HOST not found on {cfg['deploy']}")
    pod = f"account-dedup-{database}-{int(time.time())}"
    command = ["psql", "-X", "-At", "-F", "\t", "-v", "ON_ERROR_STOP=1"] + (["-1"] if single_transaction else []) + ["-c", sql]
    manifest = {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"name": pod, "namespace": NS, "labels": {"app": cfg["label"]}},
        "spec": {
            "restartPolicy": "Never", "automountServiceAccountToken": False,
            "securityContext": {"runAsNonRoot": True, "runAsUser": 70, "runAsGroup": 70,
                                "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [{
                "name": "psql", "image": "postgres:16-alpine", "command": command,
                "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                "env": [
                    {"name": "PGHOST", "value": host}, {"name": "PGSSLMODE", "value": "require"},
                    {"name": "PGDATABASE", "valueFrom": {"configMapKeyRef": {"name": "fruition-config", "key": cfg["db"]}}},
                    {"name": "PGUSER", "valueFrom": {"configMapKeyRef": {"name": "fruition-config", "key": cfg["user"]}}},
                    {"name": "PGPASSWORD", "valueFrom": {"secretKeyRef": {"name": cfg["secret"], "key": cfg["password"]}}},
                ]}]}}
    try:
        kubectl("apply", "-f", "-", input=json.dumps(manifest))
        subprocess.run(["kubectl", "-n", NS, "wait", "--for=jsonpath={.status.phase}=Succeeded",
                        f"pod/{pod}", "--timeout=180s"], capture_output=True)
        phase = kubectl("-n", NS, "get", "pod", pod, "-o", "jsonpath={.status.phase}")
        logs = kubectl("-n", NS, "logs", pod)
        if phase != "Succeeded":
            raise RuntimeError(f"{database} query failed ({phase}): {logs.strip()[-500:]}")
        return logs
    finally:
        subprocess.run(["kubectl", "-n", NS, "delete", "pod", pod, "--ignore-not-found"], capture_output=True)


def build_plan():
    users, members = parse_access(run_sql("access", ACCESS_REPORT_SQL))
    counts = parse_counts(run_sql("core", CORE_COUNT_SQL.format(ids=sql_ids(u["id"] for u in users)))) if users else {}
    return decide(users, members, counts)


def print_plan(plan):
    for g in plan["groups"]:
        keep = g["keep"]
        drops = ", ".join(f"{u['provider']}({u['docs']}) {u['id']}" for u in g["delete"])
        print(f"{g['key']}  keep {keep['provider']}({keep['docs']}) {keep['id']}  delete {drops}")
    for ws in plan["workspaces"]:
        print(f"workspace {ws['id']}: {ws['action']} {ws['user_id']}")
    deleted = sum(len(g["delete"]) for g in plan["groups"])
    print(f"emails {len(plan['groups'])}, accounts to delete {deleted}, workspace changes {len(plan['workspaces'])}")
    print(f"plan hash: {plan_hash(plan)}")


def snapshot():
    name = f"{ACCESS_INSTANCE}-account-dedup-{time.strftime('%Y%m%d%H%M%S', time.gmtime())}"
    subprocess.run(["aws", "rds", "create-db-snapshot", "--region", REGION, "--db-instance-identifier", ACCESS_INSTANCE,
                    "--db-snapshot-identifier", name], check=True, capture_output=True)
    subprocess.run(["aws", "rds", "wait", "db-snapshot-available", "--region", REGION,
                    "--db-snapshot-identifier", name], check=True)
    return name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["report", "apply"])
    parser.add_argument("--confirm")
    args = parser.parse_args()
    with tempfile.NamedTemporaryFile() as kubeconfig:
        subprocess.run(["aws", "eks", "update-kubeconfig", "--region", REGION, "--name", CLUSTER,
                        "--kubeconfig", kubeconfig.name], check=True, capture_output=True)
        import os
        os.environ["KUBECONFIG"] = kubeconfig.name
        plan = build_plan()
        print_plan(plan)
        if args.mode == "report":
            return
        if args.confirm != plan_hash(plan):
            raise SystemExit("plan hash가 report와 다릅니다. report를 다시 확인하세요.")
        if not plan["groups"]:
            print("nothing to apply")
            return
        print(f"snapshot: {snapshot()}")
        run_sql("access", apply_sql(plan), single_transaction=True)
        print("applied")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"error: {exc}\n{(exc.stderr or '').strip()[-1000:]}", file=sys.stderr)
        sys.exit(1)
    except (ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
