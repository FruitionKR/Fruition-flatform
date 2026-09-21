#!/usr/bin/env python3
"""AWS manifest 렌더와 순차 배포 gate. 실제 실행은 명시적 deploy/rollback만 허용한다."""

import argparse
import copy
import json
import ipaddress
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aws_release_safety import validate_review, smoke_settings, authenticated_smoke

import yaml

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "fruition"
CONVERTER_DEPLOYMENT = "converter"
APP_KINDS = {"ServiceAccount", "ConfigMap", "Service", "Deployment", "Job", "NetworkPolicy", "Ingress",
             "ExternalSecret", "KafkaNodePool", "Kafka", "KafkaTopic", "KafkaUser", "ScaledObject",
             "TriggerAuthentication", "PodDisruptionBudget"}
PLACEHOLDER = re.compile(r"REPLACE_ME|PLACEHOLDER|CHANGEME|<[^>]+>|\$\{[^}]+\}", re.I)
DNS = r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}"
KEYS = {"account_id", "access_rds_endpoint", "core_rds_endpoint", "redis_endpoint", "s3_bucket", "app_domain", "domain", "acm_cert_arn",
        "document_storage_role_arn", "pipeline_storage_role_arn", "vpc_cidr", "alb_subnet_cidr_1", "alb_subnet_cidr_2", "smtp_port", "waf_acl_arn"}


def run(args, *, input=None):
    return subprocess.run(args, input=input, text=True, capture_output=True, check=True).stdout


def kubectl(*args, input=None):
    return run(["kubectl", "-n", NAMESPACE, *args], input=input)


def validate(config, sha):
    if set(config) != KEYS:
        raise ValueError("배포 JSON에는 문서의 비밀 아닌 입력 키만 모두 필요합니다")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("image SHA는 게시된 릴리스의 소문자 40자리 ID여야 합니다")
    for key, value in config.items():
        if not isinstance(value, str) or not value or PLACEHOLDER.search(value):
            raise ValueError(f"유효하지 않은 입력: {key}")
    if not re.fullmatch(r"[0-9]{12}", config["account_id"]):
        raise ValueError("account_id는 12자리 숫자여야 합니다")
    for key in ("access_rds_endpoint", "core_rds_endpoint", "redis_endpoint", "app_domain", "domain"):
        if not re.fullmatch(DNS, config[key]) or ".." in config[key]:
            raise ValueError(f"호스트명만 필요합니다: {key}")
    if config["access_rds_endpoint"] == config["core_rds_endpoint"]:
        raise ValueError("Access와 Core RDS endpoint는 달라야 합니다")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", config["s3_bucket"]):
        raise ValueError("유효하지 않은 S3 bucket")
    arn = rf"arn:aws:acm:ap-northeast-2:{config['account_id']}:certificate/[0-9a-f-]{{36}}"
    if not re.fullmatch(arn, config["acm_cert_arn"]):
        raise ValueError("ACM ARN의 region/account/certificate를 확인하세요")
    if not re.fullmatch(rf"arn:aws:wafv2:ap-northeast-2:{config['account_id']}:regional/webacl/[A-Za-z0-9_-]+/[0-9a-f-]{{36}}", config["waf_acl_arn"]):
        raise ValueError("WAF ARN의 region/account/regional webacl을 확인하세요")
    for key in ("document_storage_role_arn", "pipeline_storage_role_arn"):
        if not re.fullmatch(rf"arn:aws:iam::{config['account_id']}:role/[A-Za-z0-9+=,.@_/-]+", config[key]):
            raise ValueError("서비스 S3 role ARN의 account와 형식을 확인하세요")
    if config["document_storage_role_arn"] == config["pipeline_storage_role_arn"]:
        raise ValueError("서비스별 S3 role을 분리해야 합니다")
    network = ipaddress.ip_network(config["vpc_cidr"])
    if network.version != 4 or not network.is_private:
        raise ValueError("IPv4 private VPC CIDR이 필요합니다")
    for key in ("alb_subnet_cidr_1", "alb_subnet_cidr_2"):
        subnet = ipaddress.ip_network(config[key])
        if subnet.version != 4 or not subnet.subnet_of(network) or subnet == network:
            raise ValueError("ALB subnet은 VPC에 속해야 합니다")
    if ipaddress.ip_network(config["alb_subnet_cidr_1"]).overlaps(ipaddress.ip_network(config["alb_subnet_cidr_2"])):
        raise ValueError("ALB subnet은 서로 겹치지 않아야 합니다")
    if not re.fullmatch(r"[1-9][0-9]{0,4}", config["smtp_port"]) or int(config["smtp_port"]) > 65535:
        raise ValueError("SMTP port는 1~65535 정수여야 합니다")


def render(config, sha):
    validate(config, sha)
    with tempfile.TemporaryDirectory(prefix="fruition-aws-") as directory:
        tree = Path(directory) / "k8s"
        shutil.copytree(ROOT / "k8s", tree)
        overlay = tree / "overlays/aws"
        for path in overlay.glob("*.yaml"):
            content = path.read_text()
            for key, value in config.items():
                content = content.replace("REPLACE_ME_" + key.upper(), value)
            path.write_text(content)
        path = overlay / "kustomization.yaml"
        data = yaml.safe_load(path.read_text())
        for item in data["images"]:
            item["newTag"] = sha
        path.write_text(yaml.safe_dump(data, sort_keys=False))
        content = run(["kubectl", "kustomize", str(overlay)])
    documents = list(yaml.safe_load_all(content))
    check_manifest(documents, sha)
    return documents


def check_manifest(documents, sha):
    # 주석이 아니라 실제 렌더된 값 전체를 검사한다.
    if PLACEHOLDER.search(json.dumps(documents)):
        raise ValueError("렌더 결과에 미치환 placeholder가 남았습니다")
    deployments = [d for d in documents if d["kind"] == "Deployment"]
    if not deployments:
        raise ValueError("Deployment가 없는 manifest")
    for document in documents:
        if document["kind"] not in {"Deployment", "Job"}:
            continue
        for container in document["spec"]["template"]["spec"]["containers"]:
            if not container["image"].endswith(":" + sha):
                raise ValueError("업무 image는 모두 같은 immutable SHA여야 합니다")


def apply(documents):
    if documents:
        if any(d["kind"] not in APP_KINDS or d["metadata"].get("namespace") != NAMESPACE for d in documents):
            raise ValueError("앱 배포는 fruition namespace의 허용 리소스만 변경할 수 있습니다")
        kubectl("apply", "-f", "-", input=yaml.safe_dump_all(documents, sort_keys=False))


def wait(document, condition="Ready"):
    kubectl("wait", f"{document['kind']}/{document['metadata']['name']}",
            f"--for=condition={condition}", "--timeout=600s")


def job(document):
    name = document["metadata"]["name"]
    kubectl("delete", "job", name, "--ignore-not-found=true", "--wait=true")
    apply([document])
    wait(document, "Complete")


def preflight_job(service, config, *, require_empty=False):
    prefix = {"access": "ACCESS", "document": "CORE", "ai": "AI"}[service]
    db = {"access": "access", "document": "core", "ai": "ai"}[service]
    runtime_secret = "fruition-" + ("pipeline" if service == "ai" else service)
    env = [{"name": "PGCONNECT_TIMEOUT", "value": "15"}, {"name": "PGSSLMODE", "value": "require"}]
    for role in ("runtime", "migration"):
        key = ("AI_DATABASE_URL" if role == "runtime" else "AI_DB_MIGRATION_URL") if service == "ai" else f"{prefix}_DB_{role.upper()}_PASSWORD"
        env.append({"name": role.upper() + "_CREDENTIAL", "valueFrom": {"secretKeyRef": {
            "name": runtime_secret if role == "runtime" else f"fruition-{service}-migration", "key": key}}})
    host = config["access_rds_endpoint" if service == "access" else "core_rds_endpoint"]
    # credential은 Secret에서만 주입한다. shell trace와 DB client 오류 출력은 비활성화한다.
    script = f"""set -eu
export PGHOST={host} PGPORT=5432
for role in runtime migration; do
  export PGUSER={db}_"$role"
  export PGDATABASE={db}_db
  if [ "$role" = runtime ]; then credential="$RUNTIME_CREDENTIAL"; else credential="$MIGRATION_CREDENTIAL"; fi
"""
    if service == "ai":
        # Terraform이 생성하는 단일 endpoint URI 계약만 허용한다. query의 host/sslmode 재정의를 거부한다.
        script += '''  # Terraform URI의 명시적 TLS 옵션만 허용한다. 실제 TLS는 PGSSLMODE=require로 유지.
  case "$credential" in
    *\\?sslmode=require) credential=${credential%\\?sslmode=require} ;;
  esac
  prefix="postgresql://$PGUSER:"
  suffix="@$PGHOST:$PGPORT/$PGDATABASE"
  case "$credential" in
    "$prefix"*"$suffix") ;;
    *) echo 'AI database URI contract failed'; exit 1 ;;
  esac
  password=${credential#"$prefix"}
  password=${password%"$suffix"}
  case "$password" in
    ''|*[!a-zA-Z0-9_%-]*) echo 'AI database URI password encoding failed'; exit 1 ;;
  esac
  export PGDATABASE="$credential"
'''
    else:
        script += '  export PGPASSWORD="$credential"\n'
    script += f"""  result=$(psql --dbname="$PGDATABASE" -X -A -t -v ON_ERROR_STOP=1 -v expected_user="{db}_$role" -v expected_db='{db}_db' -v migration='{db}_migration' 2>/dev/null <<'SQL'
SELECT current_user = :'expected_user' AND current_database() = :'expected_db'
 AND (SELECT pg_get_userbyid(datdba) = :'migration' FROM pg_database WHERE datname = current_database())
 AND (SELECT pg_get_userbyid(nspowner) = :'migration' FROM pg_namespace WHERE nspname = 'public')
 AND has_schema_privilege(current_user, 'public', 'USAGE')
 AND has_schema_privilege(current_user, 'public', 'CREATE') = (current_user = :'migration')
 AND NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = current_user AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls))
 AND NOT EXISTS (SELECT 1 FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname = current_user))
 AND NOT EXISTS (SELECT 1 FROM pg_database WHERE datname IN ('access_db','core_db','ai_db') AND datname <> current_database() AND has_database_privilege(current_user, oid, 'CONNECT'))
 AND NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','S','v','m') AND pg_get_userbyid(c.relowner) <> :'migration')
 AND NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) privilege WHERE n.nspname='public' AND c.relkind IN ('r','p') AND current_user <> :'migration' AND NOT has_table_privilege(current_user,c.oid,privilege));
SQL
  )
  [ "$result" = t ] || {{ echo 'DB ownership gate failed'; exit 1; }}
done
# 같은 PostgreSQL client와 schema-only dump로 실제 스키마를 비교한다. 데이터는 출력하지 않는다.
pg_dump --dbname="$PGDATABASE" --schema-only --no-owner --no-privileges --schema=public > /tmp/schema.sql 2>/dev/null
# 최신 PostgreSQL의 임의 restrict token은 스키마 내용이 아니다.
sed -E '/^\\\\(un)?restrict /d' /tmp/schema.sql > /tmp/schema-canonical.sql
sha256sum /tmp/schema-canonical.sql | cut -d ' ' -f 1
"""
    if require_empty:
        # migration credentials are still active. Reject every user object, not just rows/tables.
        empty_check = """empty=$(psql --dbname="$PGDATABASE" -X -A -t -v ON_ERROR_STOP=1 2>/dev/null <<'SQL'
SELECT NOT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname NOT IN ('public','information_schema') AND nspname !~ '^pg_')
 AND NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public')
 AND NOT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public')
 AND NOT EXISTS (SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public')
 AND NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname <> 'plpgsql');
SQL
)
[ "$empty" = t ] || { echo 'Initial install requires an empty database'; exit 1; }
"""
        script = script.replace('# 같은 PostgreSQL client', empty_check + '# 같은 PostgreSQL client')
    labels = {"app.kubernetes.io/component": "db-preflight", "app": f"{service}-db-preflight"}
    return {"apiVersion": "batch/v1", "kind": "Job",
            "metadata": {"name": f"{service}-db-preflight", "namespace": NAMESPACE, "labels": labels},
            "spec": {"backoffLimit": 0, "activeDeadlineSeconds": 600, "template": {
                "metadata": {"labels": labels},
                "spec": {"restartPolicy": "Never", "serviceAccountName": f"fruition-{service}-migration",
                         "automountServiceAccountToken": False,
                         "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001,
                                             "fsGroup": 10001, "seccompProfile": {"type": "RuntimeDefault"}},
                         "containers": [{"name": "preflight", "image": "postgres:16-alpine",
                                         "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                                         "command": ["sh", "-c", script], "env": env}]}}}}


def fingerprints(config, *, require_empty=False):
    results = {}
    for service in ("access", "document", "ai"):
        document = preflight_job(service, config, require_empty=require_empty)
        job(document)
        digest = kubectl("logs", "job/" + document["metadata"]["name"]).strip()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"{service}: DB fingerprint를 확인할 수 없습니다")
        results[service] = digest
    return results


def release_name(sha):
    return "fruition-release-" + sha


def verify_target(config):
    account = config["account_id"]
    actual = run(["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"]).strip()
    if actual != account:
        raise ValueError("AWS 인증 계정이 배포 대상과 다릅니다")
    cluster = json.loads(run(["aws", "eks", "describe-cluster", "--region", "ap-northeast-2",
                              "--name", "fruition-eks", "--output", "json"]))["cluster"]
    if (cluster["arn"] != f"arn:aws:eks:ap-northeast-2:{account}:cluster/fruition-eks"
            or cluster["version"] != "1.35" or cluster["status"] != "ACTIVE"):
        raise ValueError("EKS cluster가 feedback 대상/버전/준비 상태와 다릅니다")
    endpoint = kubectl("config", "view", "--minify", "-o", "jsonpath={.clusters[0].cluster.server}").strip()
    if endpoint != cluster["endpoint"]:
        raise ValueError("현재 Kubernetes context가 배포 대상 EKS와 다릅니다")


def wait_alb_bindings():
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        bindings = json.loads(kubectl("get", "targetgroupbindings", "-o", "json"))
        ready = {item.get("spec", {}).get("serviceRef", {}).get("name")
                 for item in bindings.get("items", []) if item.get("spec", {}).get("targetType") == "ip"
                 and item.get("spec", {}).get("targetGroupARN") and not item.get("metadata", {}).get("deletionTimestamp")}
        if {"access-svc", "document-svc"} <= ready:
            return
        time.sleep(5)
    raise ValueError("ALB TargetGroupBinding 준비 시간 초과: 앱 Pod 생성 전 중단합니다")


def access_probe_timeout_recovery(before, after):
    """Only the reviewed Access timeout 1 -> 5 change; never alter image/SQL/config."""
    try:
        original = list(yaml.safe_load_all(before))
    except yaml.YAMLError:
        return False
    if not original or any(not isinstance(d, dict) for d in original):
        return False
    updated = copy.deepcopy(after)
    old = next((d for d in original if d.get("kind") == "Deployment" and d["metadata"]["name"] == "access-svc"), None)
    new = next((d for d in updated if d.get("kind") == "Deployment" and d["metadata"]["name"] == "access-svc"), None)
    if old is None or new is None:
        return False
    old_container = old["spec"]["template"]["spec"]["containers"][0]
    new_container = new["spec"]["template"]["spec"]["containers"][0]
    for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
        previous = old_container.get(probe, {})
        current = new_container.get(probe, {})
        if previous.get("timeoutSeconds", 1) != 1 or current.get("timeoutSeconds") != 5:
            return False
        if "timeoutSeconds" in previous:
            current["timeoutSeconds"] = previous["timeoutSeconds"]
        else:
            current.pop("timeoutSeconds")
    return original == updated


def access_mail_health_recovery(before, after):
    """Only disable repetitive SMTP health authentication; keep mail delivery configured."""
    try:
        original = list(yaml.safe_load_all(before))
    except yaml.YAMLError:
        return False
    if not original or any(not isinstance(d, dict) for d in original):
        return False
    updated = copy.deepcopy(after)
    old = next((d for d in original if d.get("kind") == "Deployment" and d["metadata"]["name"] == "access-svc"), None)
    new = next((d for d in updated if d.get("kind") == "Deployment" and d["metadata"]["name"] == "access-svc"), None)
    if old is None or new is None:
        return False
    old_env = old["spec"]["template"]["spec"]["containers"][0].get("env", [])
    new_container = new["spec"]["template"]["spec"]["containers"][0]
    new_env = new_container.get("env", [])
    key = "MANAGEMENT_HEALTH_MAIL_ENABLED"
    if any(e.get("name") == key for e in old_env):
        return False
    if [e for e in new_env if e.get("name") == key] != [{"name": key, "value": "false"}]:
        return False
    new_container["env"] = [e for e in new_env if e.get("name") != key]
    return original == updated


def access_oauth_secret_recovery(before, after):
    """Only add the six reviewed OAuth references to the Access ExternalSecret."""
    try:
        original = list(yaml.safe_load_all(before))
    except yaml.YAMLError:
        return False
    if not original or any(not isinstance(d, dict) for d in original):
        return False
    updated = copy.deepcopy(after)
    def access_secret(documents):
        return [d for d in documents if d.get("kind") == "ExternalSecret"
                and d.get("metadata", {}).get("name") == "fruition-access"]
    old, new = access_secret(original), access_secret(updated)
    if len(old) != 1 or len(new) != 1:
        return False
    keys = {provider + suffix for provider in ("GOOGLE", "NAVER", "KAKAO")
            for suffix in ("_CLIENT_ID", "_CLIENT_SECRET")}
    old_data = old[0].get("spec", {}).get("data", [])
    new_data = new[0].get("spec", {}).get("data", [])
    if (not isinstance(old_data, list) or not isinstance(new_data, list)
            or any(not isinstance(entry, dict) for entry in old_data + new_data)
            or any(entry.get("secretKey") in keys for entry in old_data)):
        return False
    additions = [entry for entry in new_data if entry.get("secretKey") in keys]
    if len(additions) != 6 or {entry["secretKey"] for entry in additions} != keys:
        return False
    if any(entry != {"secretKey": entry["secretKey"], "remoteRef": {
            "key": "fruition/app", "property": entry["secretKey"]}} for entry in additions):
        return False
    new[0]["spec"]["data"] = [entry for entry in new_data if entry.get("secretKey") not in keys]
    return original == updated


def initial_install_state(config, sha, documents, bootstrap, probe_recovery=False, mail_health_recovery=False, oauth_recovery=False):
    """Bind an empty-DB installation and its promotion to the exact reviewed inputs."""
    records = json.loads(kubectl("get", "configmaps", "-o", "json")).get("items", [])
    expected = {"initial_install_contract": "1", "sha": sha,
                "config": json.dumps(config, sort_keys=True),
                "manifest": yaml.safe_dump_all(documents, sort_keys=False)}
    marker = next((r for r in records if r["metadata"]["name"] == "fruition-bootstrap"), None)
    ready = next((r for r in records if r["metadata"]["name"] == "fruition-bootstrap-ready"), None)
    successes = [r for r in records if r["metadata"]["name"].startswith("fruition-release-")]
    if successes and (bootstrap or any(r["metadata"]["name"] != release_name(sha) for r in successes)):
        raise ValueError("다른 성공 release가 있는 환경에 initial-install을 사용할 수 없습니다")
    recovery_requested = probe_recovery or mail_health_recovery
    if recovery_requested and (marker is None or ready is not None or successes):
        raise ValueError("health 복구는 기존 미완료 최초 설치에만 허용합니다")
    chain = [("fruition-bootstrap-probe-recovery", access_probe_timeout_recovery, probe_recovery),
             ("fruition-bootstrap-mail-health-recovery", access_mail_health_recovery, mail_health_recovery)]
    pending_recovery = None
    for record in (marker, ready):
        if record is not None and (record.get("immutable") is not True or
                                  any(record.get("data", {}).get(k) != v for k, v in expected.items() if k != "manifest")):
            raise ValueError("최초 설치 기록의 SHA·설정·검증 계약이 다릅니다")
    previous_manifest = marker["data"].get("manifest") if marker else None
    for name, allowed, requested in chain:
        record = next((r for r in records if r["metadata"]["name"] == name), None)
        if record is None:
            if requested and previous_manifest != expected["manifest"]:
                if not previous_manifest or not allowed(previous_manifest, documents):
                    raise ValueError("검토된 health 변경 외의 manifest 변경은 허용하지 않습니다")
                pending_recovery = install_record(name, {**expected, "original_manifest": previous_manifest})
                previous_manifest = expected["manifest"]
            continue
        data = record.get("data", {})
        if (record.get("immutable") is not True or not previous_manifest or
                any(data.get(k) != v for k, v in expected.items() if k != "manifest") or
                data.get("original_manifest") != previous_manifest or
                not isinstance(data.get("manifest"), str)):
            raise ValueError("최초 설치 health 복구 기록이 일치하지 않습니다")
        try:
            recovered = list(yaml.safe_load_all(data["manifest"]))
        except yaml.YAMLError:
            raise ValueError("최초 설치 health 복구 manifest를 읽을 수 없습니다") from None
        if not recovered or any(not isinstance(d, dict) for d in recovered) or not allowed(previous_manifest, recovered):
            raise ValueError("최초 설치 health 복구 기록에 허용되지 않은 변경이 있습니다")
        previous_manifest = data["manifest"]
    # OAuth wiring was added after bootstrap readiness. Preserve both the original
    # readiness evidence and the earlier health recovery chain during promotion.
    ready_manifest = expected["manifest"]
    oauth_name = "fruition-bootstrap-oauth-recovery"
    oauth_record = next((r for r in records if r["metadata"]["name"] == oauth_name), None)
    if oauth_recovery or oauth_record is not None:
        if bootstrap or marker is None or ready is None or (oauth_recovery and successes):
            raise ValueError("OAuth 복구는 준비 완료된 동일 SHA의 최초 deploy 전용입니다")
        if ready["data"].get("manifest") != previous_manifest:
            raise ValueError("OAuth 복구의 최초 설치 완료 기록이 기존 복구 이력과 다릅니다")
        if not access_oauth_secret_recovery(previous_manifest, documents):
            raise ValueError("Access OAuth Secret 연결 6개 추가 외의 변경은 허용하지 않습니다")
        oauth_data = {**expected, "original_manifest": previous_manifest,
                      "fingerprints": ready["data"].get("fingerprints", "")}
        if oauth_record is None:
            pending_recovery = install_record(oauth_name, oauth_data)
        elif oauth_record.get("immutable") is not True or oauth_record.get("data") != oauth_data:
            raise ValueError("최초 설치 OAuth 복구 기록이 일치하지 않습니다")
        ready_manifest = previous_manifest
        previous_manifest = expected["manifest"]
    if marker is not None and previous_manifest != expected["manifest"]:
        raise ValueError("최초 설치 manifest가 다릅니다. 변경 내용을 확인하고 해당 복구 경로를 선택하세요")
    if ready is not None and ready["data"].get("manifest") != ready_manifest:
        raise ValueError("최초 설치 완료 manifest가 다릅니다")
    apps = json.loads(kubectl("get", "deployments", "-o", "json")).get("items", [])
    names = {d["metadata"]["name"] for d in documents if d["kind"] == "Deployment"}
    apps = [a for a in apps if a["metadata"]["name"] in names]
    if apps and marker is None:
        raise ValueError("기존 앱이 있는 환경에서 최초 설치를 시작할 수 없습니다")
    if any(not c["image"].endswith(":" + sha) for a in apps for c in a["spec"]["template"]["spec"]["containers"]):
        raise ValueError("최초 설치 대상 앱 이미지 SHA가 다릅니다")
    if bootstrap and ready is not None:
        raise ValueError("최초 설치가 준비됐습니다. 같은 SHA의 deploy로 업무 검증을 완료하세요")
    if not bootstrap and (marker is None or ready is None):
        raise ValueError("initial-install deploy는 동일 SHA의 bootstrap 준비 완료 기록이 필요합니다")
    if ready is not None:
        saved = json.loads(ready["data"].get("fingerprints", "{}"))
        if set(saved) != {"access", "document", "ai"} or any(not re.fullmatch(r"[0-9a-f]{64}", v) for v in saved.values()):
            raise ValueError("최초 설치 완료 DB fingerprint 기록이 잘못됐습니다")
        if fingerprints(config) != saved:
            raise ValueError("최초 설치 완료 후 DB schema가 변경됐습니다")
    return expected, marker is None, pending_recovery


def install_record(name, data):
    return {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": name, "namespace": NAMESPACE},
            "immutable": True, "data": data}


def deploy(config, sha, documents, *, rollback=False, review=None, bootstrap=False, probe_recovery=False, mail_health_recovery=False, oauth_recovery=False):
    validate(config, sha)
    check_manifest(documents, sha)
    if not rollback:
        validate_review(review, sha)
    if bootstrap and rollback:
        raise ValueError("bootstrap과 rollback을 동시에 실행할 수 없습니다")
    if probe_recovery and mail_health_recovery:
        raise ValueError("health 복구는 한 번에 하나의 검토된 변경만 선택하세요")
    if (probe_recovery or mail_health_recovery) and (not bootstrap or rollback or review["migration_mode"] != "initial-install"):
        raise ValueError("probe 복구는 initial-install bootstrap 전용입니다")
    if oauth_recovery and (bootstrap or rollback or review["migration_mode"] != "initial-install"
                           or probe_recovery or mail_health_recovery):
        raise ValueError("OAuth 복구는 다른 복구 옵션 없는 initial-install deploy 전용입니다")
    settings = None if bootstrap else smoke_settings()
    verify_target(config)
    initial = not rollback and review["migration_mode"] == "initial-install"
    if initial:
        initial_data, needs_empty_check, recovery_record = initial_install_state(config, sha, documents, bootstrap, probe_recovery, mail_health_recovery, oauth_recovery)
    if bootstrap:
        records = json.loads(kubectl("get", "configmaps", "-o", "json")).get("items", [])
        if any(d["metadata"]["name"].startswith("fruition-release-") for d in records):
            raise ValueError("성공 release가 있는 환경은 bootstrap으로 되돌릴 수 없습니다")
        app_names = {d["metadata"]["name"] for d in documents if d["kind"] == "Deployment"}
        existing_apps = json.loads(kubectl("get", "deployments", "-o", "json")).get("items", [])
        if any(d["metadata"]["name"] in app_names for d in existing_apps):
            marker = next((d for d in records if d["metadata"]["name"] == "fruition-bootstrap"), {})
            previous = marker.get("data", {})
            if previous.get("sha") != sha or previous.get("config") != json.dumps(config, sort_keys=True):
                raise ValueError("bootstrap은 최초 설치 또는 동일 SHA의 미완료 최초 설치 재시도만 가능합니다")
            if any(not c["image"].endswith(":" + sha) for d in existing_apps if d["metadata"]["name"] in app_names
                   for c in d["spec"]["template"]["spec"]["containers"]):
                raise ValueError("bootstrap 재시도 대상 앱 이미지가 최초 설치 SHA와 다릅니다")
    # 플랫폼 리소스는 인프라 관리자가 별도로 준비한다. 앱 deployer는 읽기만 가능하다.
    namespace = json.loads(kubectl("get", "namespace", NAMESPACE, "-o", "json"))
    labels = namespace.get("metadata", {}).get("labels", {})
    if labels.get("elbv2.k8s.aws/pod-readiness-gate-inject") != "enabled" or labels.get("pod-security.kubernetes.io/enforce") != "baseline":
        raise ValueError("플랫폼 관리자가 먼저 Namespace 보안/ALB readiness 설정을 적용해야 합니다")
    kubectl("get", "storageclass", "gp3", "-o", "name")
    wait({"kind": "ClusterSecretStore", "metadata": {"name": "aws-secrets-manager"}})
    existing = kubectl("get", "configmap", release_name(sha), "--ignore-not-found", "-o", "json")
    if rollback and not existing.strip():
        raise ValueError("이전 성공 release 기록이 없습니다")
    if existing.strip():
        record = json.loads(existing)["data"]
        if record.get("safety_contract_version") != "2":
            raise ValueError("보안/배포 보호 적용 전 release는 재사용할 수 없습니다. 검토된 새 release가 필요합니다")
        expected = json.loads(record["fingerprints"])
        if json.loads(record["config"]) != config:
            raise ValueError("기존 release와 배포 환경이 다릅니다. 새 SHA가 필요합니다")
        saved_documents = list(yaml.safe_load_all(record["manifest"]))
        if not rollback and saved_documents != documents:
            raise ValueError("기존 release와 manifest가 다릅니다. 새 SHA가 필요합니다")
        documents = saved_documents
        check_manifest(documents, sha)
        # 현재 Secret과 ServiceAccount로 먼저 확인한다. 불일치 시 업무 설정도 변경하지 않는다.
        current = fingerprints(config)
        if current != expected:
            raise ValueError("기존 성공 release와 실제 DB schema가 달라 SHA 재배포를 차단합니다")
    # 모든 입력·placeholder 검증은 최초 apply 전에 끝낸다.
    if bootstrap and not initial:
        apply([{"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": "fruition-bootstrap", "namespace": NAMESPACE},
                "immutable": True, "data": {"sha": sha, "config": json.dumps(config, sort_keys=True)}}])
    if initial and recovery_record is not None:
        apply([recovery_record])
    foundation = {"ServiceAccount", "ConfigMap", "ExternalSecret", "NetworkPolicy"}
    apply([d for d in documents if d["kind"] in foundation])
    # apply는 렌더에서 제외한 기존 리소스를 지우지 않는다. 제한 정책을 먼저 준비한 뒤
    # 과거 overlay의 넓은 ingress 허용을 제거해야 정책 합집합으로 우회되지 않는다.
    kubectl("delete", "networkpolicy", "internal-only-ingress", "--ignore-not-found=true", "--wait=true")
    for document in documents:
        if document["kind"] == "ExternalSecret":
            wait(document)
    if not existing.strip():
        current = fingerprints(config, require_empty=initial and needs_empty_check)
        if initial and needs_empty_check:
            # Persist proof only AFTER all three databases passed the empty/ownership gate.
            apply([install_record("fruition-bootstrap", initial_data)])
        if review["migration_mode"] == "expand-only" or (initial and bootstrap):
            for document in documents:
                if document["kind"] == "Job":
                    job(document)
        current = fingerprints(config)
    event_kinds = {"KafkaNodePool", "Kafka", "KafkaTopic"}
    apply([d for d in documents if d["kind"] in event_kinds])
    for document in documents:
        if document["kind"] in {"Kafka", "KafkaTopic"}:
            wait(document)
    apply([d for d in documents if d["kind"] == "KafkaUser"])
    for document in documents:
        if document["kind"] == "KafkaUser":
            wait(document)
    # The ALB controller must create bindings before admission creates application Pods.
    routing = {"Service", "Ingress"}
    apply([d for d in documents if d["kind"] in routing])
    wait_alb_bindings()
    workloads = [d for d in documents if d["kind"] not in foundation | event_kinds | routing |
                 {"Namespace", "Job", "ScaledObject", "KafkaUser", "TriggerAuthentication"}]
    # New document-svc calls converter /convert-source-batch. Roll converter out and
    # confirm readiness before any other workload so documents never see an old converter.
    converter = [d for d in workloads if d["kind"] == "Deployment" and d["metadata"]["name"] == CONVERTER_DEPLOYMENT]
    if not converter:
        raise ValueError(f"{CONVERTER_DEPLOYMENT} Deployment가 manifest에 없습니다")
    apply(converter)
    kubectl("rollout", "status", "deployment/" + CONVERTER_DEPLOYMENT, "--timeout=600s")
    apply([d for d in workloads if d not in converter])
    for document in workloads:
        if document["kind"] == "Deployment" and document not in converter:
            kubectl("rollout", "status", "deployment/" + document["metadata"]["name"], "--timeout=600s")
    apply([d for d in documents if d["kind"] == "TriggerAuthentication"])
    apply([d for d in documents if d["kind"] == "ScaledObject"])
    for document in documents:
        if document["kind"] == "ScaledObject":
            wait(document)
    for host in ("api", "access"):
        response = run(["curl", "--fail", "--silent", "--show-error", "--retry", "8", "--retry-all-errors",
                        "--retry-delay", "5", "--max-time", "30", f"https://{host}.{config['domain']}/v3/api-docs"])
        body = json.loads(response)
        if not str(body.get("openapi", "")).startswith("3.") or not isinstance(body.get("paths"), dict) or not body["paths"]:
            raise ValueError(f"{host}: 유효한 OpenAPI 응답이 아닙니다")
    if bootstrap:
        if initial:
            apply([install_record("fruition-bootstrap-ready", {**initial_data, "fingerprints": json.dumps(current)})])
        print("초기 설치 완료: 검증 계정/workspace 준비 후 deploy로 업무 검증을 마치세요. 성공 release는 기록하지 않았습니다.")
        return
    authenticated_smoke(config, sha, settings=settings)
    if not existing.strip():
        record = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": release_name(sha), "namespace": NAMESPACE},
                  "immutable": True, "data": {"safety_contract_version": "2", "fingerprints": json.dumps(current), "config": json.dumps(config),
                                             "manifest": yaml.safe_dump_all(documents, sort_keys=False),
                                             "review": json.dumps(review)}}
        apply([record])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("render", "bootstrap", "deploy", "rollback"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--review", type=Path, help="검토된 릴리스별 migration/복원 시험 기록 JSON")
    parser.add_argument("--bootstrap-probe-recovery", action="store_true", help="검토된 Access probe timeout 1→5초 복구만 허용")
    parser.add_argument("--bootstrap-mail-health-recovery", action="store_true", help="SMTP 반복 health 인증 제외 복구만 허용")
    parser.add_argument("--bootstrap-oauth-recovery", action="store_true", help="준비 완료된 최초 deploy에서 Access OAuth Secret 연결 6개 추가만 허용")
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    validate(config, args.sha)
    documents = render(config, args.sha)
    if args.action == "render":
        print(yaml.safe_dump_all(documents, sort_keys=False))
    else:
        review = json.loads(args.review.read_text()) if args.review and args.action != "rollback" else None
        deploy(config, args.sha, documents, rollback=args.action == "rollback", review=review,
               bootstrap=args.action == "bootstrap", probe_recovery=args.bootstrap_probe_recovery,
               mail_health_recovery=args.bootstrap_mail_health_recovery, oauth_recovery=args.bootstrap_oauth_recovery)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        # subprocess 출력에는 provider/DB 오류가 섞일 수 있으므로 자동 로그를 내보내지 않는다.
        raise SystemExit(str(error)) from None
