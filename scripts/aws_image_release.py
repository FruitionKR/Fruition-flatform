#!/usr/bin/env python3
"""Publish tested public main revisions as one five-image release, reusing unchanged service images."""
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
    "frontend": ("FruitionKR/Fruition-frontend", ".", "Dockerfile"),
}
REPOS = sorted({s[0] for s in SERVICES.values()})
# schema 1은 frontend가 EKS로 오기 전 release다. 검증은 하되 rollback으로만 쓴다.
# schema 3부터 이미지는 release ID가 아니라 서비스별 빌드 입력 태그(b-…)와 digest로 기록한다.
SCHEMA_SERVICES = {1: ["access-svc", "document-svc", "pipeline", "converter"], 2: list(SERVICES), 3: list(SERVICES)}
SCHEMA_VERSION = 3
# publish-images.yml의 build job이 바뀌면 같은 소스여도 다른 이미지가 나올 수 있다.
# 그때 BUILDER_VERSION을 올려 모든 서비스를 다시 빌드하고, 아래 해시를 새 build job 값으로 갱신한다.
BUILDER_VERSION = 1
BUILDER_JOB_SHA256 = "e0d05c52fa1e584d6200bb19423d8f6cfe381a95644f55a2810bdb5d199f5ef2"
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


def build_id(service, repo, context_tree, dockerfile, builder):
    raw = json.dumps({"service": service, "repo": repo, "context_tree": context_tree,
                      "dockerfile": dockerfile, "builder": builder}, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()[:40]


def validate_builds(data, services):
    builder = data.get("builder_version")
    if type(builder) is not int or not 1 <= builder <= BUILDER_VERSION:
        raise ValueError("Invalid builder version")
    builds = data.get("builds", {})
    if not isinstance(builds, dict) or set(builds) != set(services):
        raise ValueError("A release must record the build inputs of every service")
    for service, build in builds.items():
        repo, _, dockerfile = SERVICES[service]
        if (not isinstance(build, dict) or set(build) != {"context_tree", "dockerfile", "tag"}
                or not isinstance(build["context_tree"], str) or not SHA.fullmatch(build["context_tree"])
                or build["dockerfile"] != dockerfile
                or build["tag"] != "b-" + build_id(service, repo, build["context_tree"], dockerfile, builder)):
            raise ValueError("Build tag does not match its recorded inputs: " + service)


def valid_image(data, service, image):
    if data["schema_version"] < 3:
        return isinstance(image, str) and bool(DIGEST.fullmatch(image))
    return (isinstance(image, dict) and set(image) == {"tag", "digest"}
            and image["tag"] == data["builds"][service]["tag"]
            and isinstance(image["digest"], str) and bool(DIGEST.fullmatch(image["digest"])))


def image_tag(data, service):
    return data["builds"][service]["tag"] if data["schema_version"] >= 3 else data["release_sha"]


def validate_manifest(data, release, complete=True):
    if not SHA.fullmatch(release) or data.get("release_sha") != release:
        raise ValueError("Invalid release identifier")
    services = SCHEMA_SERVICES.get(data.get("schema_version"))
    if services is None:
        raise ValueError("Unsupported release schema")
    sources = data.get("sources", {})
    if set(sources) != {SERVICES[s][0] for s in services} or any(not isinstance(v, str) or not SHA.fullmatch(v)
                                                                  for v in sources.values()):
        raise ValueError("Only the approved service repositories are allowed")
    recipe = data.get("recipe", "")
    if not isinstance(recipe, str) or not re.fullmatch(r"[0-9a-f]{64}", recipe):
        raise ValueError("Invalid build recipe digest")
    if identity(sources, recipe) != release:
        raise ValueError("Release content does not match its identifier")
    if data["schema_version"] >= 3:
        validate_builds(data, services)
    if complete:
        images = data.get("images", {})
        if (not isinstance(images, dict) or set(images) != set(services)
                or any(not valid_image(data, s, v) for s, v in images.items())):
            raise ValueError("A published release must contain every image digest of its schema")
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


def context_tree(repo, root, context):
    if context == ".":
        return root
    tree = github(f"repos/{repo}/git/trees/{root}")
    entry = next((e for e in tree["tree"] if e["path"] == context and e["type"] == "tree"), None)
    if entry is None:
        raise ValueError(f"Build context not found: {repo}/{context}")
    return entry["sha"]


def discover(path):
    sources, roots = {}, {}
    for repo in REPOS:
        commit = github(f"repos/{repo}/commits/main")
        sha = commit["sha"]
        runs = github(f"repos/{repo}/actions/workflows/ci.yml/runs?branch=main&event=push&head_sha={sha}&per_page=100")
        if not ci_passed(runs["workflow_runs"], sha, repo):
            print(f"Waiting for successful main CI: {repo}")
            output("ready", "false")
            return
        sources[repo] = sha
        roots[repo] = commit["commit"]["tree"]["sha"]
    # Git tree SHA는 context 안 파일 내용만으로 정해진다. 바뀌지 않은 서비스는 같은 태그를 재사용한다.
    builds = {}
    for service, (repo, context, dockerfile) in SERVICES.items():
        tree = context_tree(repo, roots[repo], context)
        builds[service] = {"context_tree": tree, "dockerfile": dockerfile,
                           "tag": "b-" + build_id(service, repo, tree, dockerfile, BUILDER_VERSION)}
    recipe = hashlib.sha256(Path(__file__).read_bytes() +
                            (ROOT / ".github/workflows/publish-images.yml").read_bytes()).hexdigest()
    release = identity(sources, recipe)
    repo = os.environ["GITHUB_REPOSITORY"]
    existing = github(f"repos/{repo}/releases/tags/images-{release}", missing_ok=True)
    if existing and not existing["draft"]:
        print(f"Already published: images-{release}")
        output("ready", "false")
        return
    data = {"schema_version": SCHEMA_VERSION, "release_sha": release, "recipe": recipe, "sources": sources,
            "builder_version": BUILDER_VERSION, "builds": builds}
    validate_manifest(data, release, complete=False)
    Path(path).write_text(json.dumps(data, indent=2) + "\n")
    output("ready", "true")
    output("release", release)


def ecr_digest(service, tag, missing_ok=False):
    result = subprocess.run(["aws", "ecr", "describe-images", "--repository-name",
                             "fruition-" + service, "--image-ids", "imageTag=" + tag,
                             "--output", "json"], text=True, capture_output=True)
    if result.returncode:
        if missing_ok and "ImageNotFoundException" in result.stderr:
            return None
        raise ValueError("Cannot read ECR image: " + service)
    digest = json.loads(result.stdout)["imageDetails"][0]["imageDigest"]
    if not DIGEST.fullmatch(digest):
        raise ValueError("Invalid ECR digest")
    return digest


def load_current(path):
    data = json.loads(Path(path).read_text())
    validate_manifest(data, data["release_sha"], complete=False)
    if data["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Only the current release schema can be published")
    return data


def prepare_build(path, service, result_path):
    data = load_current(path)
    tag = image_tag(data, service)
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
    digest = ecr_digest(service, tag, missing_ok=True)
    if digest is None:
        source = Path("source")
        subprocess.run(["git", "clone", "--no-checkout", "--filter=blob:none",
                        "https://github.com/" + repo + ".git", str(source)], check=True)
        subprocess.run(["git", "-C", str(source), "checkout", "--detach", data["sources"][repo]], check=True)
        if run(["git", "-C", str(source), "rev-parse", "HEAD"]) != data["sources"][repo]:
            raise ValueError("Source revision mismatch")
        registry = account + ".dkr.ecr.ap-northeast-2.amazonaws.com"
        image = registry + "/fruition-" + service + ":" + tag
        # Password is passed through stdin, never command arguments or logs.
        password = run(["aws", "ecr", "get-login-password", "--region", "ap-northeast-2"])
        subprocess.run(["docker", "login", "--username", "AWS", "--password-stdin", registry],
                       input=password, text=True, check=True)
        for key, value in {
            "build": "true", "registry": registry, "image": image,
            "context": str(source / context), "dockerfile": str(source / dockerfile),
            "revision": data["sources"][repo], "repository": "https://github.com/" + repo,
        }.items():
            output(key, value)
        return
    # 같은 빌드 입력의 immutable 태그가 있으면(이전 release나 재시도) 다시 빌드하지 않는다.
    print(f"Reusing {service} image {tag}")
    output("build", "false")
    Path(result_path).write_text(json.dumps({service: {"tag": tag, "digest": digest, "built": False}}) + "\n")


def record_build(path, service, result_path, expected_digest):
    data = load_current(path)
    if not DIGEST.fullmatch(expected_digest or ""):
        raise ValueError("Build action must return an image digest")
    tag = image_tag(data, service)
    digest = ecr_digest(service, tag)
    if digest != expected_digest:
        raise ValueError("Built digest does not match immutable ECR tag")
    Path(result_path).write_text(json.dumps({service: {"tag": tag, "digest": digest, "built": True}}) + "\n")


def read_results(directory):
    results = {}
    for file in Path(directory).glob("*.json"):
        result = json.loads(file.read_text())
        if set(results) & set(result):
            raise ValueError("Duplicate image result")
        results.update(result)
    return results


def finalize(path, directory):
    data = load_current(path)
    images = {}
    for service, result in read_results(directory).items():
        if not isinstance(result, dict):
            raise ValueError("Invalid image result: " + service)
        images[service] = {"tag": result.get("tag"), "digest": result.get("digest")}
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


def fetch(release, destination):
    data = fetch_release(release)
    Path(destination).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def verify(release=None, allow_legacy=False, manifest=None):
    if manifest is None:
        data = fetch_release(release)
    else:
        # render가 쓰는 바로 그 파일을 검증한다. fetch 단계가 게시 여부를 이미 확인했다.
        data = json.loads(Path(manifest).read_text())
        if release is not None and data.get("release_sha") != release:
            raise ValueError("Manifest is not the selected release")
        validate_manifest(data, data.get("release_sha", ""))
    # 이전 schema는 frontend 이미지가 없어 현재 manifest로 deploy하면 없는 태그를 받는다.
    if set(SCHEMA_SERVICES[data["schema_version"]]) != set(SERVICES) and not allow_legacy:
        raise ValueError("A release without the frontend image can only be used for rollback")
    for service, image in data["images"].items():
        digest = image["digest"] if data["schema_version"] >= 3 else image
        if ecr_digest(service, image_tag(data, service)) != digest:
            raise ValueError("Published digest does not match ECR: " + service)
    print(f"Published release and all {len(data['images'])} ECR digests verified")


def notes(path, destination, directory="results"):
    data = load_current(path)
    validate_manifest(data, data["release_sha"])
    built = {s for s, r in read_results(directory).items() if isinstance(r, dict) and r.get("built") is True}
    text = "배포할 이미지 버전: `" + data["release_sha"] + "`\n\n"
    text += "Actions → Deploy (EKS) → main → release_sha에 위 버전을 입력하고 실행하세요. feedback 운영자 승인과 릴리스 검토 기록이 필요합니다.\n\n"
    text += "| 저장소 | 소스 커밋 |\n|---|---|\n"
    text += "".join(f"| {repo} | {sha} |\n" for repo, sha in data["sources"].items())
    text += "\n| 서비스 | 이미지 태그 | 이번 게시 |\n|---|---|---|\n"
    text += "".join(f"| {s} | `{image['tag']}` | {'새로 빌드' if s in built else '재사용'} |\n"
                    for s, image in data["images"].items())
    text += "\n<!-- fruition-image-manifest\n" + json.dumps(data, sort_keys=True) + "\n-->\n"
    Path(destination).write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["discover", "prepare-build", "record-build", "finalize", "notes",
                                            "fetch", "verify"])
    parser.add_argument("--manifest")
    parser.add_argument("--service", choices=list(SERVICES))
    parser.add_argument("--results", default="results")
    parser.add_argument("--output", default="release-notes.md")
    parser.add_argument("--release")
    parser.add_argument("--digest")
    parser.add_argument("--allow-legacy", action="store_true")
    args = parser.parse_args()
    if args.command == "verify":
        if not args.release and not args.manifest:
            raise ValueError("verify needs --release or --manifest")
        return verify(args.release, args.allow_legacy, args.manifest)
    if args.command == "fetch":
        return fetch(args.release or "", args.output)
    manifest = args.manifest or "release.json"
    if args.command == "discover": discover(manifest)
    elif args.command == "prepare-build": prepare_build(manifest, args.service, args.output)
    elif args.command == "record-build": record_build(manifest, args.service, args.output, args.digest)
    elif args.command == "finalize": finalize(manifest, args.results)
    else: notes(manifest, args.output, args.results)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
