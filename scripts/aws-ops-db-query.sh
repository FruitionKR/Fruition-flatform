#!/usr/bin/env bash
# 운영 core_db(document-svc)에 읽기 전용 SQL을 실행한다. runner 호스트(세션 관리자 또는 SSM send-command)에서 실행한다.
# fruition:operators access entry(operations-query Role)로 fruition namespace에 일회성 psql Pod를 띄운다.
# DB 접속 정보는 fruition-config·fruition-secret에서 Pod 안으로만 주입되며 화면·파일에 남지 않는다.
#
# 사용: bash scripts/aws-ops-db-query.sh "SELECT count(*) FROM ai_operation_logs;"
set -eu
[ $# -eq 1 ] || { echo "usage: $0 '<SELECT ...>'" >&2; exit 2; }
SQL=$1
case "$SQL" in
  [Ss][Ee][Ll][Ee][Cc][Tt]*|[Ww][Ii][Tt][Hh]*) ;;
  *) echo "읽기 전용 SELECT/WITH 문만 허용한다." >&2; exit 2 ;;
esac

REGION=${AWS_REGION:-ap-northeast-2}
CLUSTER=${EKS_CLUSTER:-fruition-eks}
NS=fruition
POD="ops-query-$(date +%s)"
export KUBECONFIG
KUBECONFIG=$(mktemp)
trap 'kubectl -n "$NS" delete pod "$POD" --ignore-not-found >/dev/null 2>&1 || true; rm -f "$KUBECONFIG"' EXIT

aws eks update-kubeconfig --region "$REGION" --name "$CLUSTER" >/dev/null
PGHOST=$(kubectl -n "$NS" get deploy document-svc \
  -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="POSTGRES_HOST")].value}')
[ -n "$PGHOST" ] || { echo "document-svc의 POSTGRES_HOST를 읽지 못했다." >&2; exit 1; }

SQL_JSON=$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$SQL")
cat <<EOF | kubectl -n "$NS" apply -f - >/dev/null
apiVersion: v1
kind: Pod
metadata:
  name: $POD
  labels:
    app: document-svc
spec:
  restartPolicy: Never
  securityContext:
    runAsNonRoot: true
    runAsUser: 70
    runAsGroup: 70
    seccompProfile:
      type: RuntimeDefault
  containers:
  - name: psql
    image: postgres:16-alpine
    securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop: ["ALL"]
    env:
    - name: PGHOST
      value: "$PGHOST"
    - name: PGSSLMODE
      value: require
    - name: PGDATABASE
      valueFrom: { configMapKeyRef: { name: fruition-config, key: CORE_DB_NAME } }
    - name: PGUSER
      valueFrom: { configMapKeyRef: { name: fruition-config, key: CORE_DB_RUNTIME_USER } }
    - name: PGPASSWORD
      valueFrom: { secretKeyRef: { name: fruition-secret, key: CORE_DB_RUNTIME_PASSWORD } }
    command: ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-c", $SQL_JSON]
EOF
kubectl -n "$NS" wait --for=jsonpath='{.status.phase}'=Succeeded "pod/$POD" --timeout=180s >/dev/null 2>&1 || true
PHASE=$(kubectl -n "$NS" get pod "$POD" -o jsonpath='{.status.phase}')
kubectl -n "$NS" logs "$POD" || true
if [ "$PHASE" != "Succeeded" ]; then
  echo "pod phase: $PHASE" >&2
  kubectl -n "$NS" describe pod "$POD" | tail -15 >&2
  exit 1
fi
