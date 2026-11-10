#!/usr/bin/env python3
"""Probe WAF routing with synthetic text, zero IDs and NO authentication.

Allowed probes must reach the backend's authentication rejection, not mutate
documents or start paid AI jobs. Do not attach cookies or authorization tokens.
"""
import argparse
import json
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

WORKSPACE = "/api/workspaces/ws_" + "0" * 32
DOCUMENT = WORKSPACE + "/documents/doc_" + "0" * 32
SESSION = WORKSPACE + "/chat/sessions/session_" + "0" * 32
SKILL = WORKSPACE + "/skills/00000000-0000-0000-0000-000000000000"
MEETING = WORKSPACE + "/meetings/mtg_" + "0" * 32


def cases():
    routes = [
        ("upload", "POST", WORKSPACE + "/documents", "multipart"),
        ("save", "PUT", DOCUMENT + "/content", "multipart"),
        ("markdown", "POST", WORKSPACE + "/documents/markdown", "json"),
        ("agent", "POST", WORKSPACE + "/agent/turn", "json"),
        ("query", "POST", SESSION + "/query", "json"),
        ("query-run", "POST", SESSION + "/query/runs", "json"),
        ("schema-preview", "POST", WORKSPACE + "/wiki-schema/preview", "json"),
        ("schema-draft", "POST", WORKSPACE + "/wiki-schema/drafts", "json"),
        ("skill-author", "POST", WORKSPACE + "/skills/author", "json"),
        ("skill-publish", "POST", WORKSPACE + "/skills/author/publish", "json"),
        ("skill-update", "PATCH", SKILL, "json"),
        ("skill-test-run", "POST", WORKSPACE + "/skills/test-run", "json"),
        ("meeting-notes-apply", "POST", MEETING + "/notes/1/apply", "json"),
        ("speech-transcription", "POST", WORKSPACE + "/speech/transcriptions", "audio"),
        ("workspace-icon", "PUT", WORKSPACE + "/icon/image", "multipart"),
        ("profile-avatar", "PUT", "/api/auth/me/avatar", "multipart"),
    ]
    payloads = {
        "size": "정상 문서 내용입니다.\n" * 600,
        "lfi": "경로 예시: ../../../../etc/passwd",
        "xss": 'HTML 학습 예시: <script>alert("example")</script>',
        "sqli": "' OR '1'='1' --",
        # 개발 메모의 로컬 주소. GenericRFI_BODY·EC2MetaDataSSRF_BODY가 잡는다.
        "loopback": "로컬 확인: http://127.0.0.1:8080/health, http://localhost:3000/",
    }
    for name, method, path, kind in routes:
        for payload, text in payloads.items():
            yield (f"{name}-{payload}", method, path, kind, text, "auth")
    controls = [
        ("signin", "POST", "/api/auth/signin", "json"),
        ("rename", "PATCH", DOCUMENT + "/rename", "json"),
        ("ingest", "POST", DOCUMENT + "/ingest", "json"),
        ("wrong-method", "POST", DOCUMENT + "/content", "multipart"),
        ("wrong-media", "PUT", DOCUMENT + "/content", "json"),
        ("bad-workspace", "POST", WORKSPACE.replace("ws_", "bad_") + "/documents/markdown", "json"),
        ("extra-path", "POST", WORKSPACE + "/documents/markdown/extra", "json"),
        ("wrong-skill-method", "POST", SKILL, "json"),
        ("agent-approval", "POST", WORKSPACE + "/agent/runs/run_" + "0" * 32 + "/approve", "json"),
    ]
    for name, method, path, kind in controls:
        yield (f"control-{name}", method, path, kind, payloads["size"], "block")
    for payload in ("lfi", "xss", "sqli", "loopback"):
        yield (f"control-signin-{payload}", "POST", "/api/auth/signin", "json", payloads[payload], "block")
    # A document-content contract must not exempt query-string inspection.
    yield ("control-query-xss", "POST", WORKSPACE + "/documents/markdown?example=%3Cscript%3Ealert(1)%3C/script%3E", "json", "normal text", "block")
    # Document contracts tolerate loopback URLs only in the body, never in query arguments.
    yield ("control-query-loopback", "POST", WORKSPACE + "/documents/markdown?example=http://127.0.0.1:8080/", "json", "normal text", "block")
    yield ("control-speech-wrong-media", "POST", WORKSPACE + "/speech/transcriptions", "json", payloads["size"], "block")


def body(kind, text):
    if kind == "multipart":
        boundary = "fruition-waf-" + uuid.uuid4().hex
        data = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"markdown\"\r\n\r\n"
                f"{text}\r\n--{boundary}--\r\n").encode()
        return "multipart/form-data; boundary=" + boundary, data
    if kind == "audio":
        # Synthetic bytes only; WAF matches the Content-Type, the server rejects without auth.
        return "audio/webm;codecs=opus", text.encode()
    return "application/json; charset=utf-8", json.dumps({"markdown": text}, ensure_ascii=False).encode()


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    parsed = urlsplit(args.base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        parser.error("Use an HTTPS origin without credentials, query or path")
    run_id = uuid.uuid4().hex
    opener = build_opener(NoRedirect())
    results = []
    for name, method, path, kind, text, expected in cases():
        content_type, data = body(kind, text)
        request = Request(args.base_url.rstrip("/") + path, data=data, method=method, headers={
            "Content-Type": content_type,
            "User-Agent": "FruitionWafContentProbe/1.0",
            "X-Fruition-Waf-Probe": run_id + "/" + name,
        })
        try:
            with opener.open(request, timeout=30) as response:
                status, raw = response.status, response.read(2048)
        except HTTPError as error:
            status, raw = error.code, error.read(2048)
            error.close()
        try:
            error_code = json.loads(raw).get("error", {}).get("code")
        except (ValueError, AttributeError):
            error_code = None
        # Fail closed on redirects, 2xx, 429 or 5xx. Logs prove the precise WAF
        # action; a 403 alone could otherwise also be an application rejection.
        passed = status == (401 if expected == "auth" else 403)
        results.append({"case": name, "status": status, "error_code": error_code,
                        "expected": expected, "passed": passed})
        print(name, status, "PASS" if passed else "FAIL", flush=True)
    Path(args.output).write_text(json.dumps({"run_id": run_id, "results": results}, indent=2) + "\n")
    raise SystemExit(0 if all(r["passed"] for r in results) else 1)


if __name__ == "__main__":
    main()
