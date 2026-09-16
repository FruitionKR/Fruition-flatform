#!/usr/bin/env python3
"""AWS manifest 렌더와 순차 배포 gate. 실제 실행은 명시적 deploy/rollback만 허용한다."""

import argparse
import json
import ipaddress
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = "fruition"
APP_KINDS = {"ServiceAccount", "ConfigMap", "Service", "Deployment", "Job", "NetworkPolicy", "Ingress",
             "ExternalSecret", "KafkaNodePool", "Kafka", "KafkaTopic", "ScaledObject"}
PLACEHOLDER = re.compile(r"REPLACE_ME|PLACEHOLDER|CHANGEME|<[^>]+>|\$\{[^}]+\}", re.I)
DNS = r"(?=.{1,253}$)[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}"
KEYS = {"account_id", "access_rds_endpoint", "core_rds_endpoint", "redis_endpoint", "s3_bucket", "app_domain", "domain", "acm_cert_arn",
        "document_storage_role_arn", "pipeline_storage_role_arn", "vpc_cidr", "alb_subnet_cidr_1", "alb_subnet_cidr_2", "smtp_port"}


def run(args, *, input=None):
    return subprocess.run(args, input=input, text=True, capture_output=True, check=True).stdout


def kubectl(*args, input=None):
    return run(["kubectl", "-n", NAMESPACE, *args], input=input)


def validate(config, sha):
    if set(config) != KEYS:
        raise ValueError("배포 JSON에는 문서의 비밀 아닌 입력 키만 모두 필요합니다")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("image SHA는 소문자 40자리 commit SHA여야 합니다")
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


def preflight_job(service, config):
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
        script += '''  prefix="postgresql://$PGUSER:"
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
    labels = {"app.kubernetes.io/component": "db-preflight", "app": f"{service}-db-preflight"}
    return {"apiVersion": "batch/v1", "kind": "Job",
            "metadata": {"name": f"{service}-db-preflight", "namespace": NAMESPACE, "labels": labels},
            "spec": {"backoffLimit": 0, "activeDeadlineSeconds": 600, "template": {
                "metadata": {"labels": labels},
                "spec": {"restartPolicy": "Never", "serviceAccountName": f"fruition-{service}-migration",
                         "automountServiceAccountToken": False,
                         "containers": [{"name": "preflight", "image": "postgres:16-alpine",
                                         "command": ["sh", "-c", script], "env": env}]}}}}


def fingerprints(config):
    results = {}
    for service in ("access", "document", "ai"):
        document = preflight_job(service, config)
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


def deploy(config, sha, documents, *, rollback=False):
    validate(config, sha)
    check_manifest(documents, sha)
    verify_target(config)
    # 플랫폼 리소스는 인프라 관리자가 별도로 준비한다. 앱 deployer는 읽기만 가능하다.
    kubectl("get", "namespace", NAMESPACE, "-o", "name")
    kubectl("get", "storageclass", "gp3", "-o", "name")
    wait({"kind": "ClusterSecretStore", "metadata": {"name": "aws-secrets-manager"}})
    existing = kubectl("get", "configmap", release_name(sha), "--ignore-not-found", "-o", "json")
    if rollback and not existing.strip():
        raise ValueError("이전 성공 release 기록이 없습니다")
    if existing.strip():
        record = json.loads(existing)["data"]
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
    foundation = {"ServiceAccount", "ConfigMap", "ExternalSecret", "NetworkPolicy"}
    apply([d for d in documents if d["kind"] in foundation])
    # apply는 렌더에서 제외한 기존 리소스를 지우지 않는다. 제한 정책을 먼저 준비한 뒤
    # 과거 overlay의 넓은 ingress 허용을 제거해야 정책 합집합으로 우회되지 않는다.
    kubectl("delete", "networkpolicy", "internal-only-ingress", "--ignore-not-found=true", "--wait=true")
    for document in documents:
        if document["kind"] == "ExternalSecret":
            wait(document)
    if not existing.strip():
        current = fingerprints(config)
        for document in documents:
            if document["kind"] == "Job":
                job(document)
        current = fingerprints(config)
    event_kinds = {"KafkaNodePool", "Kafka", "KafkaTopic"}
    apply([d for d in documents if d["kind"] in event_kinds])
    for document in documents:
        if document["kind"] in {"Kafka", "KafkaTopic"}:
            wait(document)
    apply([d for d in documents if d["kind"] not in foundation | event_kinds | {"Namespace", "Job", "ScaledObject"}])
    for document in documents:
        if document["kind"] == "Deployment":
            kubectl("rollout", "status", "deployment/" + document["metadata"]["name"], "--timeout=600s")
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
    if not existing.strip():
        record = {"apiVersion": "v1", "kind": "ConfigMap", "metadata": {"name": release_name(sha), "namespace": NAMESPACE},
                  "immutable": True, "data": {"fingerprints": json.dumps(current), "config": json.dumps(config),
                                             "manifest": yaml.safe_dump_all(documents, sort_keys=False)}}
        apply([record])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("render", "deploy", "rollback"))
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    validate(config, args.sha)
    documents = render(config, args.sha)
    if args.action == "render":
        print(yaml.safe_dump_all(documents, sort_keys=False))
    else:
        deploy(config, args.sha, documents, rollback=args.action == "rollback")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        # subprocess 출력에는 provider/DB 오류가 섞일 수 있으므로 자동 로그를 내보내지 않는다.
        raise SystemExit(str(error)) from None
