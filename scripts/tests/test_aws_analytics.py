"""Offline analytics deployment contracts; no analytics or AWS requests."""
import json
import os
import shutil
import sys
import tempfile
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



class CombinedLauncherAnalyticsTests(unittest.TestCase):
    """Execute the real launch functions with offline service executables."""

    def run_launchers(self, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            platform = root / "platform"
            (platform / "scripts/lib").mkdir(parents=True)
            (platform / "logs").mkdir()
            for name in ("runtime.sh", "analytics.sh"):
                shutil.copy(ROOT / "scripts/lib" / name, platform / "scripts/lib" / name)
            # Keep the real functions/source order, excluding infrastructure startup.
            script = (ROOT / "scripts/dev-up.sh").read_text()
            self.assertTrue(script.endswith('main "$@"\n'))
            script = script.removesuffix('main "$@"\n') + r'''
wait_for_url() { wait "$4"; }
start_backend /fixture/java21
start_frontend
'''
            launcher = platform / "scripts/dev-up.sh"
            launcher.write_text(script)
            env = {"PATH": os.environ["PATH"], "HOME": str(root),
                   "ANALYTICS_ENABLED": "true", "ANALYTICS_ENVIRONMENT": "production",
                   "POSTHOG_PROJECT_TOKEN": "production-fixture-must-not-propagate",
                   "POSTHOG_HOST": "https://production.invalid", "APP_VERSION": "wrong-source"}
            env.update(overrides)
            versions = {}
            # Each source has a different real Git HEAD; no service checkout is touched.
            for name, relative in (("document", "Document"), ("access", "Access"),
                                   ("frontend", "frontend/web")):
                source = root / relative
                source.mkdir(parents=True)
                for args in (("init", "-q"),
                             ("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                              "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                              "commit", "-q", "--allow-empty", "-m", name)):
                    subprocess.run(["git", "-C", str(source), *args], env=env,
                                   check=True, capture_output=True)
                versions[name] = subprocess.check_output(
                    ["git", "-C", str(source), "rev-parse", "HEAD"], env=env, text=True).strip()
                executable = source / ("npm" if name == "frontend" else "gradlew")
                executable.write_text(f"#!{sys.executable}\n" +
                    "import json, os, pathlib, sys\n" +
                    "keys = ('ANALYTICS_ENABLED', 'ANALYTICS_ENVIRONMENT', "
                    "'POSTHOG_PROJECT_TOKEN', 'POSTHOG_HOST', 'APP_VERSION', "
                    "'SERVICE_ENV_FILE', 'JAVA_HOME', 'SPRING_PROFILES_ACTIVE')\n" +
                    f"pathlib.Path({str(root / (name + '.json'))!r}).write_text(" +
                    "json.dumps({'env': {key: os.environ.get(key) for key in keys}, "
                    "'args': sys.argv[1:]}))\n")
                executable.chmod(0o755)
                if name == "frontend":
                    (source / "node_modules").mkdir()
                    (source / "node").write_text("#!/bin/sh\nexit 0\n")
                    (source / "node").chmod(0o755)
                    env["PATH"] = str(source) + os.pathsep + env["PATH"]
            # A shell-loaded dotenv would replace the explicit local gate. It must
            # remain delegated through SERVICE_ENV_FILE, never sourced by dev-up.
            (platform / "infra").mkdir()
            (platform / "infra/.env").write_text(
                "LOCAL_ANALYTICS_ENABLED=true\nLOCAL_POSTHOG_PROJECT_TOKEN=dotenv-fixture\n"
                "ANALYTICS_ENABLED=true\nANALYTICS_ENVIRONMENT=production\n")
            result = subprocess.run(["bash", str(launcher)], env=env,
                                    capture_output=True, text=True, timeout=15)
            records = {name: json.loads((root / (name + ".json")).read_text())
                       for name in versions if (root / (name + ".json")).exists()}
            return result, records, versions, str(platform / "infra/.env")

    def assert_launches(self, overrides, enabled, token, host):
        result, records, versions, env_file = self.run_launchers(**overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(records), {"document", "access", "frontend"})
        self.assertEqual(len(set(versions.values())), 3)
        for name, record in records.items():
            env = record["env"]
            self.assertEqual(env["ANALYTICS_ENABLED"], enabled, name)
            self.assertEqual(env["ANALYTICS_ENVIRONMENT"], "local", name)
            self.assertEqual(env["POSTHOG_PROJECT_TOKEN"], token, name)
            self.assertEqual(env["POSTHOG_HOST"], host, name)
            self.assertEqual(env["APP_VERSION"], versions[name], name)
            if name != "frontend":
                self.assertEqual(env["SERVICE_ENV_FILE"], env_file)
                self.assertEqual(env["JAVA_HOME"], "/fixture/java21")
                self.assertEqual(env["SPRING_PROFILES_ACTIVE"], "local")
                self.assertEqual(record["args"][0], "bootRun")
            else:
                self.assertEqual(record["args"], ["run", "dev"])

    def test_combined_launcher_defaults_off_and_isolates_production(self):
        self.assert_launches({}, "false", "", "http://127.0.0.1:18080")

    def test_combined_launcher_explicit_local_opt_in(self):
        self.assert_launches({"LOCAL_ANALYTICS_ENABLED": "true",
                              "LOCAL_POSTHOG_PROJECT_TOKEN": "mock-only",
                              "LOCAL_POSTHOG_HOST": "http://127.0.0.1:19090"},
                             "true", "mock-only", "http://127.0.0.1:19090")

    def test_combined_launcher_explicit_off_survives_dotenv(self):
        self.assert_launches({"LOCAL_ANALYTICS_ENABLED": "false"},
                             "false", "", "http://127.0.0.1:18080")

    def test_combined_launcher_blank_local_token_stays_blank(self):
        self.assert_launches({"LOCAL_ANALYTICS_ENABLED": "true",
                              "LOCAL_POSTHOG_PROJECT_TOKEN": ""},
                             "true", "", "http://127.0.0.1:18080")

    def test_combined_launcher_invalid_gate_prevents_service_execution(self):
        result, records, _, _ = self.run_launchers(LOCAL_ANALYTICS_ENABLED="yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(records, {})
        self.assertIn("LOCAL_ANALYTICS_ENABLED must be true or false", result.stderr)


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
