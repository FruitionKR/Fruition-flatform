"""Release identity, main CI gating, complete publication and digest verification."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("image_release", ROOT / "scripts/aws_image_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def manifest():
    sources = {repo: str(i + 1) * 40 for i, repo in enumerate(release.REPOS)}
    recipe = "a" * 64
    return {"schema_version": 1, "sources": sources, "recipe": recipe,
            "release_sha": release.identity(sources, recipe),
            "images": {service: "sha256:" + "b" * 64 for service in release.SERVICES}}


class ImageReleaseTests(unittest.TestCase):
    def test_publication_and_deployment_permissions_are_separate(self):
        publisher = yaml.safe_load((ROOT / ".github/workflows/publish-images.yml").read_text())
        triggers = publisher.get("on", publisher.get(True))
        self.assertEqual({"schedule", "workflow_dispatch"}, set(triggers))
        self.assertIn("github.ref == 'refs/heads/main'", publisher["jobs"]["discover"]["if"])
        self.assertIn("AWS_IMAGE_PUBLISH_ENABLED", publisher["jobs"]["discover"]["if"])
        for job in publisher["jobs"].values():
            self.assertEqual("ubuntu-latest", job["runs-on"])
        self.assertEqual(["discover", "build"], publisher["jobs"]["publish"]["needs"])
        self.assertEqual("write", publisher["jobs"]["publish"]["permissions"]["contents"])
        self.assertNotIn("id-token", publisher["jobs"]["publish"]["permissions"])
        role = (ROOT / "infra/terraform/github-image-publish.tf").read_text()
        self.assertIn('${var.github_oidc_subject_prefix}:ref:refs/heads/main', role)
        self.assertIn('repository.arn', role)
        for forbidden in ('"eks:', '"secretsmanager:', '"s3:', '"ecr:Delete', '"ecr:BatchDelete'):
            self.assertNotIn(forbidden, role)
        deploy_role = (ROOT / "infra/terraform/github-oidc.tf").read_text()
        self.assertIn('${var.github_oidc_subject_prefix}:environment:${var.github_deploy_environment}', deploy_role)
        self.assertIn('replace(var.github_oidc_subject_prefix, "/@[0-9]+/", "") == "repo:${var.github_repo}"', deploy_role)
        self.assertNotIn('"ecr:PutImage"', deploy_role)
        deploy = yaml.safe_load((ROOT / ".github/workflows/deploy.yml").read_text())
        self.assertEqual("feedback", deploy["jobs"]["deploy"]["environment"])
        self.assertEqual({"workflow_dispatch"}, set(deploy.get("on", deploy.get(True))))

    def test_identity_tracks_each_service_revision_and_recipe(self):
        data = manifest()
        release.validate_manifest(data, data["release_sha"])
        self.assertEqual(data["release_sha"], release.identity(dict(reversed(list(data["sources"].items()))), data["recipe"]))
        for repo in release.REPOS:
            modified = copy.deepcopy(data)
            modified["sources"][repo] = "f" * 40
            with self.assertRaises(ValueError):
                release.validate_manifest(modified, data["release_sha"])
        modified = copy.deepcopy(data)
        modified["recipe"] = "c" * 64
        with self.assertRaises(ValueError):
            release.validate_manifest(modified, data["release_sha"])

    def test_rejects_partial_foreign_or_malformed_release(self):
        data = manifest()
        bad = []
        item = copy.deepcopy(data); del item["images"]["converter"]; bad.append(item)
        item = copy.deepcopy(data); item["images"]["converter"] = "latest"; bad.append(item)
        item = copy.deepcopy(data); item["sources"]["attacker/repo"] = "f" * 40; bad.append(item)
        item = copy.deepcopy(data); item["release_sha"] = "../main"; bad.append(item)
        for item in bad:
            with self.subTest(item=item), self.assertRaises(ValueError):
                release.validate_manifest(item, data["release_sha"])

    def test_only_latest_successful_main_push_ci_can_publish(self):
        repo = release.REPOS[0]
        good = {"head_sha": "a" * 40, "event": "push", "head_branch": "main",
                "head_repository": {"full_name": repo}, "status": "completed", "conclusion": "success"}
        self.assertTrue(release.ci_passed([good], "a" * 40, repo))
        for key, value in [("status", "queued"), ("conclusion", "failure")]:
            self.assertFalse(release.ci_passed([{**good, key: value}, good], "a" * 40, repo))
        for key, value in [("event", "pull_request"), ("head_branch", "dev"),
                           ("head_sha", "b" * 40), ("head_repository", {"full_name": "fork/repo"})]:
            self.assertFalse(release.ci_passed([{**good, key: value}], "a" * 40, repo))
        self.assertFalse(release.ci_passed([], "a" * 40, repo))

    def test_finalize_requires_all_images_and_rejects_duplicate_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); results = root / "results"; results.mkdir()
            data = manifest(); images = data.pop("images")
            path = root / "release.json"; path.write_text(json.dumps(data))
            for service, digest in images.items():
                (results / (service + ".json")).write_text(json.dumps({service: digest}))
            release.finalize(path, results)
            self.assertEqual(images, json.loads(path.read_text())["images"])
            (results / "duplicate.json").write_text(json.dumps({"pipeline": images["pipeline"]}))
            with self.assertRaises(ValueError): release.finalize(path, results)
            (results / "duplicate.json").unlink()
            (results / "pipeline.json").unlink()
            with self.assertRaises(ValueError): release.finalize(path, results)

    def test_published_notes_round_trip_and_drafts_are_not_deployable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / "release.json"; output = root / "notes.md"
            data = manifest(); path.write_text(json.dumps(data)); release.notes(path, output)
            response = {"draft": False, "prerelease": False, "body": output.read_text()}
            with patch.dict(release.os.environ, {"GITHUB_REPOSITORY": "FruitionKR/Fruition-flatform"}), patch.object(release, "github", return_value=response):
                self.assertEqual(data, release.fetch_release(data["release_sha"]))
                for field in ("draft", "prerelease"):
                    response[field] = True
                    with self.assertRaises(ValueError): release.fetch_release(data["release_sha"])
                    response[field] = False

    def test_record_build_rejects_missing_or_mismatched_action_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / "release.json"; result = root / "image.json"
            data = manifest(); path.write_text(json.dumps(data))
            digest = "sha256:" + "b" * 64
            with patch.object(release, "ecr_digest", return_value=digest):
                for value in (None, "", "latest", "sha256:" + "c" * 64):
                    with self.subTest(value=value), self.assertRaises(ValueError):
                        release.record_build(path, "pipeline", result, value)
                    self.assertFalse(result.exists())
                release.record_build(path, "pipeline", result, digest)
                self.assertEqual({"pipeline": digest}, json.loads(result.read_text()))

    def test_prepare_retry_does_not_checkout_login_or_rebuild_existing_tag(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / "release.json"; result = root / "image.json"
            path.write_text(json.dumps(manifest())); digest = "sha256:" + "b" * 64
            with patch.dict(release.os.environ, {"AWS_ACCOUNT_ID": "123456789012"}), \
                 patch.object(release, "run", side_effect=["123456789012", json.dumps({"repositories": [{"imageTagMutability": "IMMUTABLE"}]})]), \
                 patch.object(release, "ecr_digest", return_value=digest), \
                 patch.object(release.subprocess, "run") as command, patch.object(release, "output") as output:
                release.prepare_build(path, "pipeline", result)
                command.assert_not_called()
                output.assert_called_once_with("build", "false")
                self.assertEqual({"pipeline": digest}, json.loads(result.read_text()))

    def test_prepare_new_image_verifies_checkout_before_exposing_build_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); path = root / "release.json"; result = root / "image.json"
            data = manifest(); path.write_text(json.dumps(data))
            revision = data["sources"]["FruitionKR/Fruition-ai"]
            for checked_out in ("f" * 40, revision):
                with patch.dict(release.os.environ, {"AWS_ACCOUNT_ID": "123456789012"}), \
                     patch.object(release, "run", side_effect=["123456789012", json.dumps({"repositories": [{"imageTagMutability": "IMMUTABLE"}]}), checked_out, "synthetic-login-token"]), \
                     patch.object(release, "ecr_digest", return_value=None), \
                     patch.object(release.subprocess, "run") as command, patch.object(release, "output") as output:
                    if checked_out != revision:
                        with self.assertRaises(ValueError): release.prepare_build(path, "pipeline", result)
                        output.assert_not_called()
                        self.assertEqual(2, command.call_count)
                    else:
                        release.prepare_build(path, "pipeline", result)
                        values = dict(c.args for c in output.call_args_list)
                        self.assertEqual("true", values["build"])
                        self.assertEqual("source/pipeline", values["context"])
                        self.assertEqual(revision, values["revision"])
                        self.assertFalse(result.exists())  # only record after push verification

    def test_deploy_requires_matching_ecr_digest_for_every_image(self):
        data = manifest()
        with patch.object(release, "fetch_release", return_value=data), patch.object(release, "ecr_digest", return_value="sha256:" + "b" * 64) as lookup:
            release.verify(data["release_sha"])
            self.assertEqual(4, lookup.call_count)
        with patch.object(release, "fetch_release", return_value=data), patch.object(release, "ecr_digest", return_value="sha256:" + "c" * 64):
            with self.assertRaises(ValueError): release.verify(data["release_sha"])


if __name__ == "__main__":
    unittest.main()
