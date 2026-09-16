"""AWS와 로컬 manifest의 서비스 자격증명 경계를 검사한다."""

import subprocess
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
GROUPS = {
    "access-svc": "access",
    "document-svc": "document",
    "pipeline-api": "pipeline",
    "pipeline-agent-worker": "pipeline",
    "ingest-worker": "pipeline",
    "edit-event-consumer": "pipeline",
    "query-task-worker": "pipeline",
    "agent-task-worker": "pipeline",
    "maintenance-task-worker": "pipeline",
    "converter": "converter",
}
ALLOWED = {
    "access": {"ACCESS_DB_RUNTIME_PASSWORD", "JWT_SECRET", "INTERNAL_CALLBACK_TOKEN",
               "MFA_ENCRYPTION_KEY", "SPRING_MAIL_HOST", "REDIS_PASSWORD",
               "SPRING_MAIL_USERNAME", "SPRING_MAIL_PASSWORD", "MAIL_FROM"},
    "document": {"CORE_DB_RUNTIME_PASSWORD", "JWT_SECRET", "INTERNAL_CALLBACK_TOKEN",
                 "AGENT_INTERNAL_TOKEN", "REDIS_PASSWORD"},
    "pipeline": {"AI_DATABASE_URL", "INTERNAL_CALLBACK_TOKEN", "AGENT_INTERNAL_TOKEN",
                 "REDIS_PASSWORD", "OPENAI_API_KEY", "GEMINI_API_KEY",
                 "ANTHROPIC_API_KEY", "LANGSMITH_API_KEY", "TAVILY_API_KEY"},
    "converter": {"OPENAI_API_KEY", "GEMINI_API_KEY", "ANTHROPIC_API_KEY"},
}


def render(path: str) -> list[dict]:
    result = subprocess.run(["kubectl", "kustomize", path], cwd=ROOT,
                            check=True, capture_output=True, text=True)
    return list(yaml.safe_load_all(result.stdout))


class CredentialsTest(unittest.TestCase):
    def test_aws_runtime_allowlists_and_migration_jobs(self) -> None:
        manifests = render("k8s/overlays/aws")
        secrets = {m["spec"]["target"]["name"]: {d["secretKey"] for d in m["spec"]["data"]}
                   for m in manifests if m["kind"] == "ExternalSecret"}
        accounts = {m["metadata"]["name"] for m in manifests if m["kind"] == "ServiceAccount"}
        seen = set()
        for manifest in manifests:
            if manifest["kind"] != "Deployment":
                continue
            name = manifest["metadata"]["name"]
            group = GROUPS[name]
            seen.add(name)
            pod = manifest["spec"]["template"]["spec"]
            self.assertEqual(pod["serviceAccountName"], "fruition-" + group)
            self.assertIn(pod["serviceAccountName"], accounts)
            self.assertFalse(pod["automountServiceAccountToken"])
            keys = set()
            for container in pod["containers"]:
                for ref in container.get("envFrom", []):
                    if "secretRef" in ref:
                        self.assertEqual(ref["secretRef"]["name"], "fruition-" + group)
                        keys.update(secrets[ref["secretRef"]["name"]])
                for env in container.get("env", []):
                    if "secretKeyRef" in env.get("valueFrom", {}):
                        ref = env["valueFrom"]["secretKeyRef"]
                        self.assertEqual(ref["name"], "fruition-" + group)
                        self.assertIn(ref["key"], secrets[ref["name"]])
                        keys.add(ref["key"])
            self.assertEqual(keys, ALLOWED[group], name)
        self.assertEqual(seen, set(GROUPS))
        jobs = {m["metadata"]["name"]: m for m in manifests if m["kind"] == "Job"}
        expected = {"access-migration": {"ACCESS_DB_MIGRATION_PASSWORD"},
                    "document-migration": {"CORE_DB_MIGRATION_PASSWORD"},
                    "ai-migration": {"AI_DB_MIGRATION_URL"}}
        self.assertEqual(set(jobs), set(expected))
        for name, allowed in expected.items():
            job = jobs[name]
            self.assertEqual(job["metadata"]["labels"]["app.kubernetes.io/component"], "migration")
            self.assertEqual(job["spec"]["backoffLimit"], 0)
            pod = job["spec"]["template"]["spec"]
            self.assertEqual(pod["serviceAccountName"], "fruition-" + name)
            container = pod["containers"][0]
            refs = container["envFrom"]
            self.assertEqual(len(refs), 1)
            self.assertEqual(secrets[refs[0]["secretRef"]["name"]], allowed)
            self.assertTrue(container.get("args") == ["--migrate-only"] or
                            container.get("command") == ["python", "-m",
                            "app.modules.wiki_ingestion.infrastructure.migrate_ai_schema"])

    def test_kind_only_injects_own_secrets(self) -> None:
        local_migration = {"access": {"ACCESS_DB_MIGRATION_PASSWORD"},
                           "document": {"CORE_DB_MIGRATION_PASSWORD"},
                           "pipeline": {"AI_DB_MIGRATION_URL"}, "converter": set()}
        for manifest in render("k8s/base"):
            if manifest["kind"] != "Deployment":
                continue
            group = GROUPS[manifest["metadata"]["name"]]
            for container in manifest["spec"]["template"]["spec"]["containers"]:
                self.assertFalse(any("secretRef" in r for r in container.get("envFrom", [])))
                keys = {env["valueFrom"]["secretKeyRef"]["key"] for env in container.get("env", [])
                        if "secretKeyRef" in env.get("valueFrom", {})}
                self.assertLessEqual(keys, ALLOWED[group] | local_migration[group] | ({"S3_ACCESS_KEY", "S3_SECRET_KEY"} if group in {"document", "pipeline"} else set()))
                self.assertTrue(local_migration[group] <= keys)


if __name__ == "__main__":
    unittest.main()
