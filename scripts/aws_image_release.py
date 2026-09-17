#!/usr/bin/env python3
"""Publish tested public main revisions as one immutable four-image release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib import request, error

ROOT = Path(__file__).resolve().parents[1]
SERVICES = {
    "access-svc": ("FruitionKR/Fruition-access", ".", "Dockerfile"),
    "document-svc": ("FruitionKR/Fruition-document", ".", "Dockerfile"),
    "pipeline": ("FruitionKR/Fruition-ai", "pipeline", "pipeline/Dockerfile"),
    "converter": ("FruitionKR/Fruition-ai", ".", "converter/Dockerfile"),
}
REPOS = sorted({s[0] for s in SERVICES.values()})
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def run(args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs).strip()


def github(path, missing_ok=False):
    req = request.Request("https://api.github.com/" + path, headers={
        "Authorization": "Bearer " + os.environ["GH_TOKEN"],
        "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with request.urlopen(req, timeout=60) as response:
            return json.load(response)
    except error.HTTPError as exc:
        status = exc.code
        exc.close()
        if missing_ok and status == 404:
            return None
        raise ValueError(f"GitHub API request failed ({status})") from None


def identity(sources, recipe):
    raw = json.dumps({"sources": sources, "recipe": recipe}, sort_keys=True,
                     separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()[:40]


def validate_manifest(data, release, complete=True):
    if not SHA.fullmatch(release) or data.get("release_sha") != release:
        raise ValueError("Invalid release identifier")
    sources = data.get("sources", {})
    if set(sources) != set(REPOS) or any(not isinstance(v, str) or not SHA.fullmatch(v)
                                        for v in sources.values()):
        raise ValueError("Only the three approved service repositories are allowed")
    recipe = data.get("recipe", "")
    if not isinstance(recipe, str) or not re.fullmatch(r"[0-9a-f]{64}", recipe):
        raise ValueError("Invalid build recipe digest")
    if identity(sources, recipe) != release or data.get("schema_version") != 1:
        raise ValueError("Release content does not match its identifier")
    if complete:
        images = data.get("images", {})
        if set(images) != set(SERVICES) or any(not isinstance(v, str) or not DIGEST.fullmatch(v)
                                              for v in images.values()):
            raise ValueError("A published release must contain exactly four image digests")
    return data


def ci_passed(runs, sha, repo):
    # GitHub returns newest runs first. A newer queued/failed rerun must block publication.
    candidates = [r for r in runs if r.get("head_sha") == sha and r.get("event") == "push"
                  and r.get("head_branch") == "main"
                  and r.get("head_repository", {}).get("full_name") == repo]
    return bool(candidates and candidates[0].get("status") == "completed"
                and candidates[0].get("conclusion") == "success")


def output(name, value):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as out:
            out.write(f"{name}={value}\n")


def discover(path):
    sources = {}
    for repo in REPOS:
        sha = github(f"repos/{repo}/commits/main")["sha"]
        runs = github(f"repos/{repo}/actions/workflows/ci.yml/runs?branch=main&event=push&head_sha={sha}&per_page=100")
        if not ci_passed(runs["workflow_runs"], sha, repo):
            print(f"Waiting for successful main CI: {repo}")
            output("ready", "false")
            return
        sources[repo] = sha
    recipe = hashlib.sha256(Path(__file__).read_bytes() +
                            (ROOT / ".github/workflows/publish-images.yml").read_bytes()).hexdigest()
    release = identity(sources, recipe)
    repo = os.environ["GITHUB_REPOSITORY"]
    existing = github(f"repos/{repo}/releases/tags/images-{release}", missing_ok=True)
    if existing and not existing["draft"]:
        print(f"Already published: images-{release}")
        output("ready", "false")
        return
    data = {"schema_version": 1, "release_sha": release, "recipe": recipe, "sources": sources}
    validate_manifest(data, release, complete=False)
    Path(path).write_text(json.dumps(data, indent=2) + "\n")
    output("ready", "true")
    output("release", release)


def ecr_digest(service, release, missing_ok=False):
    result = subprocess.run(["aws", "ecr", "describe-images", "--repository-name",
                             "fruition-" + service, "--image-ids", "imageTag=" + release,
                             "--output", "json"], text=True, capture_output=True)
    if result.returncode:
        if missing_ok and "ImageNotFoundException" in result.stderr:
            return None
        raise ValueError("Cannot read ECR image: " + service)
    digest = json.loads(result.stdout)["imageDetails"][0]["imageDigest"]
    if not DIGEST.fullmatch(digest):
        raise ValueError("Invalid ECR digest")
    return digest


def build(path, service, result_path):
    data = json.loads(Path(path).read_text())
    release = data["release_sha"]
    validate_manifest(data, release, complete=False)
    repo, context, dockerfile = SERVICES[service]
    account = os.environ["AWS_ACCOUNT_ID"]
    if not re.fullmatch(r"[0-9]{12}", account):
        raise ValueError("AWS_ACCOUNT_ID must be 12 digits")
    if run(["aws", "sts", "get-caller-identity", "--query", "Account", "--output", "text"]) != account:
        raise ValueError("Wrong AWS publishing account")
    repository = json.loads(run(["aws", "ecr", "describe-repositories", "--repository-names",
                                 "fruition-" + service]))["repositories"][0]
    if repository["imageTagMutability"] != "IMMUTABLE":
        raise ValueError("ECR tags must be immutable")
    digest = ecr_digest(service, release, missing_ok=True)
    if digest is None:
        source = Path("source")
        subprocess.run(["git", "clone", "--no-checkout", "--filter=blob:none",
                        "https://github.com/" + repo + ".git", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", data["sources"][repo]], check=True)
        if run(["git", "-C", str(source), "rev-parse", "HEAD"]) != data["sources"][repo]:
            raise ValueError("Source revision mismatch")
        registry = account + ".dkr.ecr.ap-northeast-2.amazonaws.com"
        image = registry + "/fruition-" + service + ":" + release
        # Password is passed through stdin, never command arguments or logs.
        password = run(["aws", "ecr", "get-login-password", "--region", "ap-northeast-2"])
        subprocess.run(["docker", "login", "--username", "AWS", "--password-stdin", registry],
                       input=password, text=True, check=True)
        try:
            subprocess.run(["docker", "build", "--platform", "linux/amd64", "--pull",
                            "--label", "org.opencontainers.image.revision=" + data["sources"][repo],
                            "--label", "org.opencontainers.image.source=https://github.com/" + repo,
                            "-f", str(source / dockerfile), "-t", image, str(source / context)], check=True)
            subprocess.run(["docker", "push", image], check=True)
        finally:
            subprocess.run(["docker", "logout", registry], check=False)
        digest = ecr_digest(service, release)
    Path(result_path).write_text(json.dumps({service: digest}) + "\n")


def finalize(path, directory):
    data = json.loads(Path(path).read_text())
    images = {}
    for file in Path(directory).glob("*.json"):
        result = json.loads(file.read_text())
        if set(images) & set(result):
            raise ValueError("Duplicate image result")
        images.update(result)
    data["images"] = images
    validate_manifest(data, data["release_sha"])
    Path(path).write_text(json.dumps(data, indent=2) + "\n")


def fetch_release(release):
    if not SHA.fullmatch(release):
        raise ValueError("Select a published 40-character release ID")
    repo = os.environ["GITHUB_REPOSITORY"]
    data = github(f"repos/{repo}/releases/tags/images-{release}")
    if data["draft"] or data["prerelease"]:
        raise ValueError("Release is not published")
    # Manifest is also in the release body: no cross-host auth redirects or runner gh dependency.
    prefix = "<!-- fruition-image-manifest\n"
    body = data.get("body") or ""
    if body.count(prefix) != 1:
        raise ValueError("Published image manifest missing")
    raw = body.split(prefix, 1)[1].split("\n-->", 1)[0]
    return validate_manifest(json.loads(raw), release)


def verify(release):
    data = fetch_release(release)
    for service, digest in data["images"].items():
        if ecr_digest(service, release) != digest:
            raise ValueError("Published digest does not match ECR: " + service)
    print("Published release and all four ECR digests verified")


def notes(path, destination):
    data = json.loads(Path(path).read_text())
    validate_manifest(data, data["release_sha"])
    text = "배포할 이미지 버전: `" + data["release_sha"] + "`\n\n"
    text += "Actions → Deploy (EKS) → main → release_sha에 위 버전을 입력하고 실행하세요. feedback 운영자 승인과 릴리스 검토 기록이 필요합니다.\n\n"
    text += "| 저장소 | 소스 커밋 |\n|---|---|\n"
    text += "".join(f"| {repo} | {sha} |\n" for repo, sha in data["sources"].items())
    text += "\n<!-- fruition-image-manifest\n" + json.dumps(data, sort_keys=True) + "\n-->\n"
    Path(destination).write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["discover", "build", "finalize", "notes", "verify"])
    parser.add_argument("--manifest", default="release.json")
    parser.add_argument("--service", choices=list(SERVICES))
    parser.add_argument("--results", default="results")
    parser.add_argument("--output", default="release-notes.md")
    parser.add_argument("--release")
    args = parser.parse_args()
    if args.command == "discover": discover(args.manifest)
    elif args.command == "build": build(args.manifest, args.service, args.output)
    elif args.command == "finalize": finalize(args.manifest, args.results)
    elif args.command == "notes": notes(args.manifest, args.output)
    else: verify(args.release)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
