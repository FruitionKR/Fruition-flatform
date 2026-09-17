"""Release review and authenticated smoke checks; never print credentials or responses."""

import json
import os
import re
import time
import sys
import uuid
from urllib import request, error


def validate_review(review, sha):
    required = {"release_sha", "migration_mode", "compatibility_test_url", "restore_test_url"}
    if not isinstance(review, dict) or set(review) != required:
        raise ValueError("릴리스 검토 파일의 필수 항목을 확인하세요")
    if review["release_sha"] != sha:
        raise ValueError("검토한 release SHA와 배포 SHA가 다릅니다")
    if review["migration_mode"] not in {"expand-only", "none"}:
        raise ValueError("온라인 배포는 expand-only 또는 none migration만 허용합니다")
    for key in ("compatibility_test_url", "restore_test_url"):
        if not isinstance(review[key], str) or not re.fullmatch(
                r"https://github\.com/FruitionKR/[A-Za-z0-9_.-]+/(actions/runs/[0-9]+|issues/[0-9]+|pull/[0-9]+)(?:#[A-Za-z0-9_-]+)?", review[key]):
            raise ValueError(f"실제로 수행한 시험의 GitHub 기록 URL이 필요합니다: {key}")
    # These URLs are reviewer attestations, not an automated proof of SQL compatibility.


def smoke_settings():
    values = {name: os.environ.get(name, "") for name in (
        "AWS_SMOKE_EMAIL", "AWS_SMOKE_PASSWORD", "AWS_SMOKE_WORKSPACE_ID")}
    if not all(values.values()):
        raise ValueError("전용 검증 계정 AWS_SMOKE_EMAIL/PASSWORD/WORKSPACE_ID가 필요합니다")
    if not re.fullmatch(r"ws_[0-9a-f]{32}", values["AWS_SMOKE_WORKSPACE_ID"]):
        raise ValueError("검증 workspace ID는 ws_와 32자리 소문자 16진수여야 합니다")
    return values


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def authenticated_smoke(config, sha, *, settings=None):
    settings = settings or smoke_settings()
    opener = request.build_opener(NoRedirect())
    access = f"https://access.{config['domain']}"
    documents = f"https://api.{config['domain']}/api/workspaces/{settings['AWS_SMOKE_WORKSPACE_ID']}/documents"

    def call(method, url, payload=None, token=None, expected=(200,), key=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        if key:
            headers["Idempotency-Key"] = key
        req = request.Request(url, method=method, headers=headers,
                              data=None if payload is None else json.dumps(payload).encode())
        try:
            with opener.open(req, timeout=30) as response:
                if response.status not in expected:
                    raise ValueError("업무 smoke 응답 상태가 예상과 다릅니다")
                raw = response.read(1048576)
                body = json.loads(raw) if raw else {}
                if not isinstance(body, dict):
                    raise ValueError("업무 smoke 응답은 JSON 객체여야 합니다")
                return body
        except (error.URLError, ValueError) as exc:
            # Close HTTP error bodies as well; delayed ResourceWarnings can expose reason text.
            if isinstance(exc, error.HTTPError):
                exc.close()
            # Server bodies and URLs can carry credentials or user content.
            raise ValueError("업무 smoke 요청 실패: 운영 로그에서 상태를 확인하세요") from None

    token = call("POST", access + "/api/auth/login", {
        "email": settings["AWS_SMOKE_EMAIL"], "password": settings["AWS_SMOKE_PASSWORD"]}).get("access_token")
    if not isinstance(token, str) or not token:
        raise ValueError("검증 계정 로그인 실패")
    result = call("POST", documents + "/markdown", {
        "display_name": "Deployment smoke " + sha[:12],
        "markdown": "# Deployment smoke\nThis document checks storage and AI ingestion.\n"},
        token, expected=(201,), key="deploy-smoke-" + str(uuid.uuid4()))
    document_id = result.get("id")
    if not isinstance(document_id, str) or not re.fullmatch(r"doc_[0-9a-f]{32}", document_id):
        raise ValueError("검증 문서 ID를 확인할 수 없습니다")
    document_url = documents + "/" + document_id
    # Only our newly created document is deleted. Never touch pre-existing user data.
    failed = False
    try:
        call("GET", document_url, token=token)
        call("POST", document_url + "/ingest", token=token, expected=(202,))
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            status = call("GET", document_url, token=token).get("status")
            if status == "completed":
                return
            if status == "failed":
                raise ValueError("검증 AI 작업 실패")
            time.sleep(5)
        raise ValueError("검증 AI 작업 완료 제한시간 초과")
    except Exception:
        failed = True
        raise
    finally:
        # Delete uses the current optimistic-lock version and a fresh idempotency key.
        # It moves the document to trash; generated wiki output may remain.
        try:
            version = call("GET", document_url, token=token).get("current_version")
            if type(version) is not int or version < 1:
                raise ValueError("검증 문서 정리를 위한 current_version을 확인할 수 없습니다")
            call("DELETE", document_url, {"base_version": version}, token=token,
                 expected=(200, 202, 204), key="deploy-smoke-cleanup-" + str(uuid.uuid4()))
        except Exception:
            if not failed:
                raise
            # Preserve the original smoke error while still reporting failed cleanup safely.
            print("검증 문서 정리도 실패했습니다. 전용 검증 workspace에서 확인하세요.", file=sys.stderr)
