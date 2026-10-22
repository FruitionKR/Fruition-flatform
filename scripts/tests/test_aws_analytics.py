"""Offline analytics deployment contracts; no analytics or AWS requests."""
import os
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class LocalAnalyticsTests(unittest.TestCase):
    def run_local(self, **overrides):
        env = {k: v for k, v in os.environ.items() if not k.startswith("LOCAL_")}
        env.update(ANALYTICS_ENABLED="true", ANALYTICS_ENVIRONMENT="production",
                   POSTHOG_PROJECT_TOKEN="production-fixture-must-not-propagate")
        env.update(overrides)
        return subprocess.run(["bash", "-c",
            'source scripts/lib/analytics.sh; local_analytics_env "$PWD" || exit $?; '
            'printf "%s\\n" "$ANALYTICS_ENABLED" "$ANALYTICS_ENVIRONMENT" '
            '"$POSTHOG_PROJECT_TOKEN" "$POSTHOG_HOST" "$APP_VERSION"'],
            cwd=ROOT, env=env, capture_output=True, text=True)

    def test_production_environment_is_not_inherited(self):
        result = self.run_local()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.splitlines()[:4],
                         ["false", "local", "", "http://127.0.0.1:18080"])
        self.assertRegex(result.stdout.splitlines()[4], r"^[0-9a-f]{40}$")

    def test_local_opt_in_and_invalid_flag(self):
        result = self.run_local(LOCAL_ANALYTICS_ENABLED="true", LOCAL_POSTHOG_PROJECT_TOKEN="mock-only")
        self.assertEqual(result.stdout.splitlines()[:3], ["true", "local", "mock-only"])
        self.assertNotEqual(self.run_local(LOCAL_ANALYTICS_ENABLED="yes").returncode, 0)

    def test_kind_config_is_disabled_and_has_no_token(self):
        doc = yaml.safe_load((ROOT / "k8s/base/configmap.yaml").read_text())
        self.assertEqual(doc["data"]["ANALYTICS_ENABLED"], "false")
        self.assertEqual(doc["data"]["POSTHOG_PROJECT_TOKEN"], "")
        self.assertEqual(doc["data"]["ANALYTICS_ENVIRONMENT"], "local")
        self.assertNotIn("ANALYTICS_ENABLED", doc["metadata"])

    def test_compose_only_uses_local_opt_in(self):
        for file in ("compose.ai.yml", "compose.containerized.yml"):
            doc = yaml.safe_load((ROOT / "infra" / file).read_text())
            for name, service in doc["services"].items():
                env = service.get("environment", {})
                if name == "embedding-server" or not ("AI_DATABASE_URL" in env or "SPRING_PROFILES_ACTIVE" in env):
                    continue
                self.assertEqual(env["ANALYTICS_ENABLED"], "${LOCAL_ANALYTICS_ENABLED:-false}", name)
                self.assertEqual(env["POSTHOG_PROJECT_TOKEN"], "${LOCAL_POSTHOG_PROJECT_TOKEN:-}", name)
                self.assertEqual(env["ANALYTICS_ENVIRONMENT"], "local", name)



class DeploymentAnalyticsTests(unittest.TestCase):
    def test_runtime_versions_flags_and_scope(self):
        from test_aws_deploy import deploy, CONFIG, CURRENT, CURRENT_SHA
        for enabled in ("false", "true"):
            docs = deploy.render({**CONFIG, "analytics_enabled": enabled}, CURRENT_SHA, CURRENT)
            seen = set()
            for doc in docs:
                if doc["kind"] != "Deployment":
                    continue
                name = doc["metadata"]["name"]
                container = doc["spec"]["template"]["spec"]["containers"][0]
                env = {e["name"]: e for e in container.get("env", [])}
                if name in {"converter", "embedding-server"}:
                    self.assertNotIn("POSTHOG_PROJECT_TOKEN", env)
                    continue
                seen.add(name)
                service = name if name in deploy.SERVICES else "pipeline"
                self.assertEqual(env["APP_VERSION"]["value"], CURRENT["sources"][deploy.SERVICES[service][0]])
                self.assertEqual(env["ANALYTICS_ENABLED"]["value"], enabled)
                self.assertEqual(env["ANALYTICS_ENVIRONMENT"]["value"], "production")
                self.assertEqual(env["POSTHOG_HOST"]["value"], "https://us.i.posthog.com")
                self.assertEqual(env["POSTHOG_PROJECT_TOKEN"]["valueFrom"]["secretKeyRef"],
                                 {"name": "fruition-analytics", "key": "POSTHOG_PROJECT_TOKEN", "optional": True})
            self.assertEqual(len(seen), 10)

    def test_default_off_and_invalid_flags(self):
        from test_aws_deploy import deploy, CONFIG, CURRENT, CURRENT_SHA
        docs = deploy.render(CONFIG, CURRENT_SHA, CURRENT)
        self.assertTrue(all(e["value"] == "false" for d in docs if d["kind"] == "Deployment"
                            for c in d["spec"]["template"]["spec"]["containers"]
                            for e in c.get("env", []) if e["name"] == "ANALYTICS_ENABLED"))
        for invalid in (True, "TRUE", "yes", "", "phc_fixture"):
            with self.assertRaises(ValueError):
                deploy.validate({**CONFIG, "analytics_enabled": invalid}, CURRENT_SHA)

    def test_enabled_preflight_rejects_missing_token_without_logging_it(self):
        from test_aws_deploy import deploy, CONFIG
        job = deploy.preflight_job("access", {**CONFIG, "analytics_enabled": "true"})
        container = job["spec"]["template"]["spec"]["containers"][0]
        # Run only the token gate; the DB commands must never execute in this test.
        script = container["command"][-1].split("export PGHOST=", 1)[0]
        for token, valid in (("", False), ("phx_private-fixture", False), ("phc_", False), ("phc_ ", False), ("phc_mock-only", True)):
            result = subprocess.run(["sh", "-c", script], env={"POSTHOG_PROJECT_TOKEN": token},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode == 0, valid)
            if token:
                self.assertNotIn(token, result.stdout + result.stderr)
        disabled = deploy.preflight_job("access", CONFIG)["spec"]["template"]["spec"]["containers"][0]
        self.assertNotIn("POSTHOG_PROJECT_TOKEN", str(disabled))

    def test_optional_secret_replaces_all_extracted_credentials(self):
        doc = yaml.safe_load((ROOT / "k8s/overlays/aws/analytics-secret.yaml").read_text())
        self.assertEqual(doc["spec"]["dataFrom"], [{"extract": {"key": "fruition/app"}}])
        template = doc["spec"]["target"]["template"]
        self.assertEqual(template["engineVersion"], "v2")
        self.assertEqual(template["mergePolicy"], "Replace")
        self.assertEqual(template["data"], {"POSTHOG_PROJECT_TOKEN": '{{ index . "POSTHOG_PROJECT_TOKEN" | default "" }}'})

if __name__ == "__main__":
    unittest.main()
