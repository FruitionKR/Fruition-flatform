"""실제 kustomize와 가짜 cluster/HTTP로 AWS 배포 순서와 실패 gate를 검사한다."""

import copy
import hashlib
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("aws_deploy", ROOT / "scripts/aws_deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

SHA = "a" * 40
REVIEW = {"release_sha": SHA, "migration_mode": "expand-only", "compatibility_test_url": "https://github.com/FruitionKR/Fruition-flatform/actions/runs/1", "restore_test_url": "https://github.com/FruitionKR/Fruition-flatform/issues/1"}
CONFIG = {
    "waf_acl_arn": "arn:aws:wafv2:ap-northeast-2:123456789012:regional/webacl/fruition-cost/00000000-0000-0000-0000-000000000000",
    "account_id": "123456789012",
    "document_storage_role_arn": "arn:aws:iam::123456789012:role/fruition-document-storage",
    "pipeline_storage_role_arn": "arn:aws:iam::123456789012:role/fruition-pipeline-storage",
    "vpc_cidr": "10.0.0.0/16",
    "alb_subnet_cidr_1": "10.0.101.0/24",
    "alb_subnet_cidr_2": "10.0.102.0/24",
    "smtp_port": "587",
    "access_rds_endpoint": "access.abc.ap-northeast-2.rds.amazonaws.com",
    "core_rds_endpoint": "core.abc.ap-northeast-2.rds.amazonaws.com",
    "redis_endpoint": "cache.abc.ap-northeast-2.cache.amazonaws.com",
    "s3_bucket": "fruition-test-artifacts",
    "app_domain": "app.fruition.test",
    "domain": "fruition.test",
    "acm_cert_arn": "arn:aws:acm:ap-northeast-2:123456789012:certificate/12345678-1234-1234-1234-123456789012",
}


class FakeCluster:
    def __init__(self, fail=None, record=None, fingerprint="b" * 64, smoke=None):
        self.events = []
        self.fail = fail
        self.record = record
        self.fingerprint = fingerprint
        self.smoke = smoke or {"openapi": "3.0.1", "paths": {"/test": {}}}
        self.policies = {"internal-only-ingress"}

    def run(self, args, *, input=None):
        self.events.append((args, list(yaml.safe_load_all(input)) if input else []))
        if self.fail and any(self.fail in arg for arg in args):
            raise subprocess.CalledProcessError(1, args)
        if args[:2] == ["aws", "sts"]:
            return CONFIG["account_id"]
        if args[:2] == ["aws", "eks"]:
            return json.dumps({"cluster": {"arn": f"arn:aws:eks:ap-northeast-2:{CONFIG['account_id']}:cluster/fruition-eks",
                                           "endpoint": "https://fixture.eks.amazonaws.com", "version": "1.35", "status": "ACTIVE"}})
        if "config" in args and "view" in args:
            return "https://fixture.eks.amazonaws.com"
        if args[0] == "kubectl" and args[3:5] == ["delete", "networkpolicy"]:
            self.policies.discard(args[5])
        for document in self.events[-1][1]:
            if document["kind"] == "NetworkPolicy":
                self.policies.add(document["metadata"]["name"])
        if args[0] == "curl":
            return json.dumps(self.smoke)
        if "logs" in args:
            return self.fingerprint
        if "get" in args and "namespace" in args:
            return json.dumps({"metadata": {"labels": {"elbv2.k8s.aws/pod-readiness-gate-inject": "enabled", "pod-security.kubernetes.io/enforce": "baseline"}}})
        if "get" in args and "targetgroupbindings" in args:
            return json.dumps({"items": [{"spec": {"targetType": "ip", "targetGroupARN": "fixture", "serviceRef": {"name": name}}} for name in ("access-svc", "document-svc")]})
        if "get" in args and "configmaps" in args:
            return json.dumps({"items": []})
        if "get" in args:
            return json.dumps(self.record) if self.record else ""
        return ""

    def applied(self, kind):
        return [d for _, documents in self.events for d in documents if d["kind"] == kind]


class DeploymentTests(unittest.TestCase):
    def test_waf_is_required_and_bound_to_same_account_and_region(self):
        documents = deploy.render(CONFIG, SHA)
        ingress = next(d for d in documents if d["kind"] == "Ingress")
        self.assertEqual(CONFIG["waf_acl_arn"], ingress["metadata"]["annotations"]["alb.ingress.kubernetes.io/wafv2-acl-arn"])
        for arn in ("none", CONFIG["waf_acl_arn"].replace("123456789012", "999999999999"),
                    CONFIG["waf_acl_arn"].replace("ap-northeast-2", "us-east-1"),
                    CONFIG["waf_acl_arn"].replace("regional/", "global/")):
            with self.subTest(arn=arn), self.assertRaises(ValueError):
                deploy.validate({**CONFIG, "waf_acl_arn": arn}, SHA)
        missing = {k: v for k, v in CONFIG.items() if k != "waf_acl_arn"}
        with self.assertRaises(ValueError):
            deploy.validate(missing, SHA)

    def setUp(self):
        settings = patch.object(deploy, "smoke_settings", return_value={"test": "fixture"})
        smoke = patch.object(deploy, "authenticated_smoke")
        settings.start()
        smoke.start()
        self.addCleanup(settings.stop)
        self.addCleanup(smoke.stop)

    @classmethod
    def setUpClass(cls):
        cls.documents = deploy.render(CONFIG, SHA)

    def test_render_preserves_sources_and_replaces_all_placeholders(self):
        paths = sorted((ROOT / "k8s").rglob("*.yaml"))
        before = {p: hashlib.sha256(p.read_bytes()).digest() for p in paths}
        documents = deploy.render(CONFIG, SHA)
        self.assertEqual(before, {p: hashlib.sha256(p.read_bytes()).digest() for p in paths})
        self.assertFalse(deploy.PLACEHOLDER.search(json.dumps(documents)))
        self.assertEqual(10, sum(d["kind"] == "Deployment" for d in documents))

    def test_invalid_inputs_fail_without_cluster_mutation(self):
        for key in CONFIG:
            for value in ("", "REPLACE_ME", "https://bad host"):
                with self.subTest(key=key, value=value):
                    config = {**CONFIG, key: value}
                    fake = FakeCluster()
                    with patch.object(deploy, "run", fake.run), self.assertRaises(ValueError):
                        deploy.deploy(config, SHA, self.documents, review=REVIEW)
                    self.assertFalse(fake.events)
        with self.assertRaises(ValueError):
            deploy.render(CONFIG, "latest")

    def test_leftover_placeholder_blocks_before_apply(self):
        documents = copy.deepcopy(self.documents)
        documents[0]["metadata"]["annotations"] = {"unknown": "REPLACE_ME_FUTURE"}
        fake = FakeCluster()
        with patch.object(deploy, "run", fake.run), self.assertRaises(ValueError):
            deploy.deploy(CONFIG, SHA, documents, review=REVIEW)
        self.assertFalse(fake.events)

    def test_platform_is_read_only_and_application_scope_is_enforced(self):
        fake = FakeCluster()
        with patch.object(deploy, "run", fake.run):
            deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW)
            for kind, namespace in (("Namespace", "fruition"), ("ClusterRole", "fruition"), ("ConfigMap", "other")):
                with self.assertRaises(ValueError):
                    deploy.apply([{"kind": kind, "metadata": {"name": "test", "namespace": namespace}}])
        for _, documents in fake.events:
            for document in documents:
                self.assertIn(document["kind"], deploy.APP_KINDS)
                self.assertEqual("fruition", document["metadata"]["namespace"])
        platform = list(yaml.safe_load_all(subprocess.check_output(
            ["kubectl", "kustomize", str(ROOT / "k8s/platform/aws")], text=True)))
        for document in platform:
            if document["kind"] == "ClusterRole":
                for rule in document["rules"]:
                    self.assertTrue(set(rule["verbs"]) <= {"get", "list", "watch"})
                    self.assertTrue(rule["resourceNames"])
            if document["kind"] == "Role":
                self.assertEqual("fruition", document["metadata"]["namespace"])
                for rule in document["rules"]:
                    self.assertFalse(set(rule["resources"]) & {"secrets", "roles", "rolebindings", "*"})
                    self.assertNotIn("*", rule["verbs"])

    def test_wrong_application_target_fails_before_any_apply(self):
        for mismatch in ("account", "context"):
            fake = FakeCluster()
            def target_runner(args, *, input=None):
                response = fake.run(args, input=input)
                if mismatch == "account" and args[:2] == ["aws", "sts"]:
                    return "999999999999"
                if mismatch == "context" and "config" in args and "view" in args:
                    return "https://another.eks.amazonaws.com"
                return response
            with self.subTest(mismatch=mismatch), patch.object(deploy, "run", target_runner), self.assertRaises(ValueError):
                deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW)
            self.assertFalse(any(documents for _, documents in fake.events))

    def test_success_orders_gates_and_covers_every_workload(self):
        fake = FakeCluster()
        with patch.object(deploy, "run", fake.run):
            deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW)
        events = [args for args, _ in fake.events]
        waits = [args[4] for args in events if len(args) > 4 and args[3] == "wait"]
        for document in self.documents:
            kind, name = document["kind"], document["metadata"]["name"]
            if kind in {"ExternalSecret", "Kafka", "KafkaTopic", "ScaledObject"}:
                self.assertIn(f"{kind}/{name}", waits)
            if kind == "Deployment":
                self.assertTrue(any(f"deployment/{name}" in args for args in events))
        first_runtime = next(i for i, (_, docs) in enumerate(fake.events) if any(d["kind"] == "Deployment" for d in docs))
        migration_waits = [i for i, (args, _) in enumerate(fake.events) if args[3] == "wait" and args[4] in {"Job/access-migration", "Job/document-migration", "Job/ai-migration"}]
        self.assertEqual(3, len(migration_waits))
        self.assertTrue(all(i < first_runtime for i in migration_waits))
        bindings = next(i for i, (args, _) in enumerate(fake.events) if "targetgroupbindings" in args)
        routes = [i for i, (_, docs) in enumerate(fake.events) if any(d["kind"] == "Ingress" for d in docs)]
        users = [i for i, (args, _) in enumerate(fake.events) if any(a.startswith("KafkaUser/") for a in args)]
        self.assertTrue(routes and routes[0] < bindings < first_runtime)
        self.assertTrue(users and all(i < first_runtime for i in users))
        self.assertEqual(2, sum(args[0] == "curl" for args in events))
        self.assertTrue(any(d["metadata"]["name"] == deploy.release_name(SHA) for d in fake.applied("ConfigMap")))

    def test_failed_secret_preflight_or_migration_prevents_runtime(self):
        for failure in ("ExternalSecret/fruition-access", "Job/access-db-preflight", "Job/document-migration"):
            fake = FakeCluster(fail=failure)
            with self.subTest(failure=failure), patch.object(deploy, "run", fake.run), self.assertRaises(subprocess.CalledProcessError):
                deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW)
            self.assertFalse(fake.applied("Deployment"))

    def test_failed_worker_keda_or_smoke_does_not_record_success(self):
        for failure in ("deployment/query-task-worker", "ScaledObject/", "curl"):
            fake = FakeCluster(fail=failure)
            with self.subTest(failure=failure), patch.object(deploy, "run", fake.run), self.assertRaises(subprocess.CalledProcessError):
                deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW)
            self.assertFalse(any(d["metadata"]["name"] == deploy.release_name(SHA) for d in fake.applied("ConfigMap")))
        fake = FakeCluster(smoke={"status": "ok"})
        with patch.object(deploy, "run", fake.run), self.assertRaises(ValueError):
            deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW)

    def test_rollback_requires_actual_matching_schema_and_skips_migrations(self):
        record = {"data": {"safety_contract_version": "2", "config": json.dumps(CONFIG), "fingerprints": json.dumps(dict.fromkeys(("access", "document", "ai"), "b" * 64)),
                           "manifest": yaml.safe_dump_all(self.documents)}}
        for digest, success in (("b" * 64, True), ("c" * 64, False)):
            fake = FakeCluster(record=record, fingerprint=digest)
            with patch.object(deploy, "run", fake.run):
                if success:
                    deploy.deploy(CONFIG, SHA, self.documents, rollback=True)
                else:
                    with self.assertRaises(ValueError):
                        deploy.deploy(CONFIG, SHA, self.documents, rollback=True)
            self.assertFalse(any(d["metadata"]["name"].endswith("-migration") for d in fake.applied("Job")))
            self.assertEqual(success, bool(fake.applied("Deployment")))
            if not success:
                self.assertFalse(fake.applied("ConfigMap"))
                self.assertFalse(fake.applied("ExternalSecret"))

    def test_preflight_secrets_are_service_scoped_and_have_network_labels(self):
        for service in ("access", "document", "ai"):
            document = deploy.preflight_job(service, CONFIG)
            pod = document["spec"]["template"]
            self.assertEqual("db-preflight", pod["metadata"]["labels"]["app.kubernetes.io/component"])
            env = pod["spec"]["containers"][0]["env"]
            refs = [item["valueFrom"]["secretKeyRef"] for item in env if "valueFrom" in item]
            runtime = "pipeline" if service == "ai" else service
            self.assertEqual({f"fruition-{runtime}", f"fruition-{service}-migration"}, {ref["name"] for ref in refs})
            self.assertEqual(2, len(refs))
            self.assertFalse(any("ADMIN" in ref["key"] for ref in refs))

    def test_existing_sha_requires_same_config_manifest_and_actual_schema(self):
        record = {"data": {"safety_contract_version": "2", "config": json.dumps(CONFIG), "fingerprints": json.dumps(dict.fromkeys(("access", "document", "ai"), "b" * 64)),
                           "manifest": yaml.safe_dump_all(self.documents)}}
        for mismatch in (None, "config", "manifest", "schema"):
            config = dict(CONFIG)
            documents = copy.deepcopy(self.documents)
            if mismatch == "config":
                config["app_domain"] = "new.fruition.test"
            if mismatch == "manifest":
                documents[0]["metadata"]["annotations"] = {"changed": "true"}
            fake = FakeCluster(record=record, fingerprint=("c" if mismatch == "schema" else "b") * 64)
            with self.subTest(mismatch=mismatch), patch.object(deploy, "run", fake.run):
                if mismatch:
                    with self.assertRaises(ValueError):
                        deploy.deploy(config, SHA, documents, review=REVIEW)
                    self.assertFalse(fake.applied("ConfigMap"))
                    self.assertFalse(fake.applied("ExternalSecret"))
                    self.assertFalse(fake.applied("Deployment"))
                else:
                    deploy.deploy(config, SHA, documents, review=REVIEW)
                    self.assertEqual(10, len(fake.applied("Deployment")))
                self.assertFalse(any(d["metadata"]["name"].endswith("-migration") for d in fake.applied("Job")))
                self.assertFalse(any(d["metadata"]["name"] == deploy.release_name(SHA) for d in fake.applied("ConfigMap")))

    def test_review_and_smoke_inputs_are_required_before_mutation(self):
        fake = FakeCluster()
        with patch.object(deploy, "run", fake.run), self.assertRaises(ValueError):
            deploy.deploy(CONFIG, SHA, self.documents)
        self.assertFalse(fake.events)
        with patch.object(deploy, "run", fake.run), patch.object(deploy, "smoke_settings", side_effect=ValueError("missing")), self.assertRaises(ValueError):
            deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW)
        self.assertFalse(fake.events)

    def test_failed_authenticated_smoke_does_not_record_success(self):
        fake = FakeCluster()
        with patch.object(deploy, "run", fake.run), patch.object(deploy, "authenticated_smoke", side_effect=ValueError("login failed")), self.assertRaises(ValueError):
            deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW)
        self.assertFalse(any(d["metadata"]["name"] == deploy.release_name(SHA) for d in fake.applied("ConfigMap")))

    def test_none_mode_skips_migrations_and_legacy_records_are_rejected(self):
        fake = FakeCluster()
        with patch.object(deploy, "run", fake.run):
            deploy.deploy(CONFIG, SHA, self.documents, review={**REVIEW, "migration_mode": "none"})
        self.assertFalse(any(d["metadata"]["name"].endswith("-migration") for d in fake.applied("Job")))
        old = FakeCluster(record={"data": {}})
        with patch.object(deploy, "run", old.run), self.assertRaisesRegex(ValueError, "보안/배포"):
            deploy.deploy(CONFIG, SHA, self.documents, rollback=True)
        self.assertFalse(old.applied("Deployment"))

    def test_bootstrap_allows_operator_but_not_existing_apps_and_never_records_success(self):
        for name in ("strimzi-cluster-operator", "access-svc"):
            fake = FakeCluster()
            def run(args, *, input=None):
                if "get" in args and "deployments" in args:
                    return json.dumps({"items": [{"metadata": {"name": name}}]})
                return fake.run(args, input=input)
            with patch.object(deploy, "run", run), patch.object(deploy, "authenticated_smoke") as smoke:
                if name == "access-svc":
                    with self.assertRaises(ValueError):
                        deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW, bootstrap=True)
                    self.assertFalse(fake.applied("Deployment"))
                else:
                    deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW, bootstrap=True)
                smoke.assert_not_called()
            self.assertFalse(any(d["metadata"]["name"] == deploy.release_name(SHA) for d in fake.applied("ConfigMap")))

    def test_bootstrap_resume_is_limited_to_same_unfinished_release(self):
        for scenario in ("same", "different_image", "successful_release"):
            fake = FakeCluster()
            def run(args, *, input=None):
                if "get" in args and "configmaps" in args:
                    items = [{"metadata": {"name": "fruition-bootstrap"},
                              "data": {"sha": SHA, "config": json.dumps(CONFIG, sort_keys=True)}}]
                    if scenario == "successful_release":
                        items.append({"metadata": {"name": deploy.release_name(SHA)}})
                    return json.dumps({"items": items})
                if "get" in args and "deployments" in args:
                    doc = copy.deepcopy(next(d for d in self.documents if d["kind"] == "Deployment"))
                    if scenario == "different_image":
                        doc["spec"]["template"]["spec"]["containers"][0]["image"] = "other:" + "b" * 40
                    return json.dumps({"items": [doc]})
                return fake.run(args, input=input)
            with patch.object(deploy, "run", run):
                if scenario == "same":
                    deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW, bootstrap=True)
                else:
                    with self.assertRaises(ValueError):
                        deploy.deploy(CONFIG, SHA, self.documents, review=REVIEW, bootstrap=True)
                    self.assertFalse(fake.applied("Deployment"))


class InitialInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = deploy.render(CONFIG, SHA)
        cls.review = {"release_sha": SHA, "migration_mode": "initial-install",
                      "installation_test_url": REVIEW["compatibility_test_url"], "restore_test_url": REVIEW["restore_test_url"]}

    def state(self, ready=False):
        data = {"initial_install_contract": "1", "sha": SHA, "config": json.dumps(CONFIG, sort_keys=True),
                "manifest": yaml.safe_dump_all(self.documents, sort_keys=False)}
        records = [deploy.install_record("fruition-bootstrap", data)]
        if ready:
            records.append(deploy.install_record("fruition-bootstrap-ready", {**data, "fingerprints": json.dumps(dict.fromkeys(("access", "document", "ai"), "b" * 64))}))
        return records

    def execute(self, records=(), apps=(), *, bootstrap=True, fail=None, fingerprint="b" * 64, smoke_error=False, probe_recovery=False, mail_health_recovery=False, oauth_recovery=False):
        fake = FakeCluster(fail=fail, fingerprint=fingerprint)
        def run(args, *, input=None):
            if "get" in args and "configmaps" in args:
                return json.dumps({"items": records})
            if "get" in args and "deployments" in args:
                return json.dumps({"items": apps})
            return fake.run(args, input=input)
        with patch.object(deploy, "run", run), patch.object(deploy, "smoke_settings", return_value={}), patch.object(deploy, "authenticated_smoke", side_effect=ValueError("smoke failed") if smoke_error else None) as smoke:
            try:
                deploy.deploy(CONFIG, SHA, self.documents, review=self.review, bootstrap=bootstrap, probe_recovery=probe_recovery, mail_health_recovery=mail_health_recovery, oauth_recovery=oauth_recovery)
            except (ValueError, subprocess.CalledProcessError) as error:
                return fake, smoke.call_count, error
        return fake, smoke.call_count, None

    def test_empty_gate_precedes_marker_and_migrations_ready_is_not_success(self):
        fake, smoke, error = self.execute()
        self.assertIsNone(error)
        self.assertEqual(smoke, 0)
        applied = [d for _, docs in fake.events for d in docs]
        marker = next(i for i,d in enumerate(applied) if d["metadata"]["name"] == "fruition-bootstrap")
        preflight = [i for i,d in enumerate(applied) if d["kind"] == "Job" and d["metadata"]["name"].endswith("db-preflight")]
        self.assertEqual(len([i for i in preflight if i < marker]), 3)
        for i in preflight[:3]:
            self.assertIn("Initial install requires an empty database", applied[i]["spec"]["template"]["spec"]["containers"][0]["command"][2])
        self.assertTrue(any(d["metadata"]["name"] == "fruition-bootstrap-ready" for d in applied))
        self.assertFalse(any(d["metadata"]["name"].startswith("fruition-release-") for d in applied))
        fake, _, error = self.execute(fail="job/ai-db-preflight")
        self.assertIsNotNone(error)
        self.assertFalse(any(d["metadata"]["name"].startswith("fruition-bootstrap") for d in fake.applied("ConfigMap")))
        self.assertFalse(any(d["metadata"]["name"].endswith("-migration") for d in fake.applied("Job")))

    def test_resume_rejects_changed_inputs_even_before_any_app_exists(self):
        for key,value in (("sha", "c"*40), ("config", "{}"), ("manifest", "changed"), ("initial_install_contract", "0")):
            records = self.state(); records[0]["data"][key] = value
            fake, _, error = self.execute(records)
            self.assertIsNotNone(error, key)
            self.assertFalse(fake.applied("Job"))
        records=self.state(); records[0]["immutable"]=False
        self.assertIsNotNone(self.execute(records)[2])
        app=copy.deepcopy(next(d for d in self.documents if d["kind"]=="Deployment"))
        self.assertIsNotNone(self.execute(apps=[app])[2])
        app["spec"]["template"]["spec"]["containers"][0]["image"]="other:"+"c"*40
        self.assertIsNotNone(self.execute(self.state(),[app])[2])
        records=self.state()+[{"metadata":{"name":deploy.release_name(SHA)}}]
        self.assertIsNotNone(self.execute(records)[2])
        fake, _, error=self.execute(self.state())
        self.assertIsNone(error)
        self.assertFalse(any("Initial install requires an empty database" in d["spec"]["template"]["spec"]["containers"][0]["command"][2] for d in fake.applied("Job") if d["metadata"]["name"].endswith("db-preflight")))

    def test_promotion_requires_ready_record_matching_schema_and_successful_smoke(self):
        for records in ([], self.state()):
            fake, _, error=self.execute(records,bootstrap=False)
            self.assertIsNotNone(error)
            self.assertFalse(fake.applied("Deployment"))
        fake, _, error=self.execute(self.state(True),bootstrap=False,fingerprint="c"*64)
        self.assertIsNotNone(error)
        self.assertFalse(fake.applied("Deployment"))
        for fail in (False,True):
            fake, smoke, error=self.execute(self.state(True),bootstrap=False,smoke_error=fail)
            self.assertEqual(smoke,1)
            self.assertEqual(error is not None,fail)
            self.assertFalse(any(d["metadata"]["name"].endswith("-migration") for d in fake.applied("Job")))
            self.assertEqual(any(d["metadata"]["name"]==deploy.release_name(SHA) for d in fake.applied("ConfigMap")),not fail)
        self.assertIsNotNone(self.execute(self.state(True))[2])

    def legacy_probe_state(self):
        records = self.state()
        old = copy.deepcopy(self.documents)
        access = next(d for d in old if d["kind"] == "Deployment" and d["metadata"]["name"] == "access-svc")
        for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
            access["spec"]["template"]["spec"]["containers"][0][probe].pop("timeoutSeconds")
        records[0]["data"]["manifest"] = yaml.safe_dump_all(old, sort_keys=False)
        return records

    def test_probe_recovery_requires_explicit_flag_and_preserves_original_record(self):
        records = self.legacy_probe_state()
        fake, _, error = self.execute(records)
        self.assertIsNotNone(error)
        self.assertFalse(fake.applied("Job"))
        fake, _, error = self.execute(records, probe_recovery=True)
        self.assertIsNone(error)
        receipts = {d["metadata"]["name"]: d for d in fake.applied("ConfigMap")}
        self.assertNotIn("fruition-bootstrap", receipts)
        recovery = receipts["fruition-bootstrap-probe-recovery"]
        self.assertTrue(recovery["immutable"])
        self.assertEqual(recovery["data"]["original_manifest"], records[0]["data"]["manifest"])
        resumed = records + [recovery]
        self.assertIsNone(self.execute(resumed)[2])
        completed = resumed + [receipts["fruition-bootstrap-ready"]]
        fake, smoke, error = self.execute(completed, bootstrap=False)
        self.assertIsNone(error)
        self.assertEqual(smoke, 1)
        recovery["data"]["original_manifest"] = "tampered"
        self.assertIsNotNone(self.execute(resumed)[2])

    def test_probe_recovery_cannot_change_images_paths_resources_or_other_deployments(self):
        for field in ("image", "resources", "path", "timeout", "other"):
            records = self.legacy_probe_state()
            old = list(yaml.safe_load_all(records[0]["data"]["manifest"]))
            name = "document-svc" if field == "other" else "access-svc"
            c = next(d for d in old if d["kind"] == "Deployment" and d["metadata"]["name"] == name)["spec"]["template"]["spec"]["containers"][0]
            if field in ("image", "other"):
                c["image"] = "unexpected:" + SHA
            elif field == "resources":
                c["resources"]["requests"]["cpu"] = "999m"
            elif field == "path":
                c["startupProbe"]["httpGet"]["path"] = "/wrong"
            else:
                c["startupProbe"]["timeoutSeconds"] = 2
            records[0]["data"]["manifest"] = yaml.safe_dump_all(old, sort_keys=False)
            fake, _, error = self.execute(records, probe_recovery=True)
            self.assertIsNotNone(error, field)
            self.assertFalse(fake.applied("Job"))
        self.assertIsNotNone(self.execute(probe_recovery=True)[2])
        self.assertIsNotNone(self.execute(self.state(True), bootstrap=False, probe_recovery=True)[2])
        self.assertFalse(deploy.access_probe_timeout_recovery("invalid", self.documents))

    def pre_mail_state(self, include_probe_receipt=False):
        records = self.state()
        before = copy.deepcopy(self.documents)
        container = next(d for d in before if d["kind"] == "Deployment" and d["metadata"]["name"] == "access-svc")["spec"]["template"]["spec"]["containers"][0]
        container["env"] = [e for e in container["env"] if e["name"] != "MANAGEMENT_HEALTH_MAIL_ENABLED"]
        before_text = yaml.safe_dump_all(before, sort_keys=False)
        records[0]["data"]["manifest"] = before_text
        if include_probe_receipt:
            for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
                container[probe].pop("timeoutSeconds")
            original = yaml.safe_dump_all(before, sort_keys=False)
            records[0]["data"]["manifest"] = original
            records.append(deploy.install_record("fruition-bootstrap-probe-recovery", {**records[0]["data"], "manifest": before_text, "original_manifest": original}))
        return records

    def test_smtp_health_recovery_keeps_probe_chain_and_requires_explicit_approval(self):
        for prior_probe in (False, True):
            records = self.pre_mail_state(prior_probe)
            self.assertIsNotNone(self.execute(records)[2])
            fake, _, error = self.execute(records, mail_health_recovery=True)
            self.assertIsNone(error)
            receipts = {d["metadata"]["name"]:d for d in fake.applied("ConfigMap")}
            self.assertNotIn("fruition-bootstrap", receipts)
            self.assertNotIn("fruition-bootstrap-probe-recovery", receipts)
            recovery = receipts["fruition-bootstrap-mail-health-recovery"]
            self.assertEqual(recovery["data"]["original_manifest"], records[-1]["data"]["manifest"])
            resumed = records + [recovery]
            self.assertIsNone(self.execute(resumed)[2])
            self.assertIsNone(self.execute(resumed + [receipts["fruition-bootstrap-ready"]], bootstrap=False)[2])
        self.assertIsNotNone(self.execute(mail_health_recovery=True)[2])
        self.assertIsNotNone(self.execute(self.state(True), bootstrap=False, mail_health_recovery=True)[2])
        self.assertIsNotNone(self.execute(self.pre_mail_state(), probe_recovery=True, mail_health_recovery=True)[2])

    def test_smtp_health_recovery_rejects_mail_credentials_and_arbitrary_config_changes(self):
        for field in ("smtp", "image", "redis", "path"):
            records = self.pre_mail_state()
            old = list(yaml.safe_load_all(records[0]["data"]["manifest"]))
            c = next(d for d in old if d["kind"] == "Deployment" and d["metadata"]["name"] == "access-svc")["spec"]["template"]["spec"]["containers"][0]
            if field == "image": c["image"] = "different:" + SHA
            elif field == "path": c["readinessProbe"]["httpGet"]["path"] = "/different"
            else: c["env"].append({"name":"SPRING_MAIL_PASSWORD" if field == "smtp" else "MANAGEMENT_HEALTH_REDIS_ENABLED", "value":"fixture"})
            records[0]["data"]["manifest"] = yaml.safe_dump_all(old, sort_keys=False)
            fake, _, error = self.execute(records, mail_health_recovery=True)
            self.assertIsNotNone(error, field)
            self.assertFalse(fake.applied("Deployment"))
        records = self.pre_mail_state(True)
        records[1]["data"]["original_manifest"] = "tampered"
        self.assertIsNotNone(self.execute(records, mail_health_recovery=True)[2])

    def test_failed_rollout_does_not_create_ready_receipt(self):
        fake, _, error=self.execute(fail="deployment/access-svc")
        self.assertIsNotNone(error)
        self.assertFalse(any(d["metadata"]["name"]=="fruition-bootstrap-ready" for d in fake.applied("ConfigMap")))

    def pre_oauth_state(self, health_chain=False):
        old = copy.deepcopy(self.documents)
        access = next(d for d in old if d["kind"] == "ExternalSecret" and d["metadata"]["name"] == "fruition-access")
        access["spec"]["data"] = [e for e in access["spec"]["data"]
                                  if not e["secretKey"].startswith(("GOOGLE_", "NAVER_", "KAKAO_"))]
        ready_text = yaml.safe_dump_all(old, sort_keys=False)
        records = self.state(True)
        for record in records:
            record["data"]["manifest"] = ready_text
        if health_chain:
            container = next(d for d in old if d["kind"] == "Deployment" and d["metadata"]["name"] == "access-svc")["spec"]["template"]["spec"]["containers"][0]
            container["env"] = [e for e in container["env"] if e["name"] != "MANAGEMENT_HEALTH_MAIL_ENABLED"]
            before_mail = yaml.safe_dump_all(old, sort_keys=False)
            for probe in ("startupProbe", "readinessProbe", "livenessProbe"):
                container[probe].pop("timeoutSeconds")
            original = yaml.safe_dump_all(old, sort_keys=False)
            records[0]["data"]["manifest"] = original
            records.extend([
                deploy.install_record("fruition-bootstrap-probe-recovery", {**records[0]["data"], "original_manifest": original, "manifest": before_mail}),
                deploy.install_record("fruition-bootstrap-mail-health-recovery", {**records[0]["data"], "original_manifest": before_mail, "manifest": ready_text}),
            ])
        return records

    def test_oauth_promotion_preserves_readiness_health_chain_and_never_migrates(self):
        for chain in (False, True):
            records = self.pre_oauth_state(chain)
            original = copy.deepcopy(records)
            fake, _, error = self.execute(records, bootstrap=False)
            self.assertIsNotNone(error)
            self.assertFalse(fake.applied("ConfigMap"))
            fake, smoke, error = self.execute(records, bootstrap=False, oauth_recovery=True)
            self.assertIsNone(error)
            self.assertEqual(smoke, 1)
            self.assertEqual(records, original)
            receipts = {d["metadata"]["name"]: d for d in fake.applied("ConfigMap")}
            self.assertFalse(set(receipts) & {r["metadata"]["name"] for r in records})
            receipt = receipts["fruition-bootstrap-oauth-recovery"]
            self.assertTrue(receipt["immutable"])
            self.assertEqual(receipt["data"]["original_manifest"], records[1]["data"]["manifest"])
            self.assertEqual(receipt["data"]["fingerprints"], records[1]["data"]["fingerprints"])
            self.assertIn(deploy.release_name(SHA), receipts)
            self.assertFalse(any(d["metadata"]["name"].endswith("-migration") for d in fake.applied("Job")))
            fake, smoke, error = self.execute(records + [receipt], bootstrap=False)
            self.assertIsNone(error)
            self.assertEqual(smoke, 1)
            self.assertNotIn("fruition-bootstrap-oauth-recovery", {d["metadata"]["name"] for d in fake.applied("ConfigMap")})

    def test_oauth_promotion_checks_schema_and_smoke_and_allows_failed_smoke_retry(self):
        records = self.pre_oauth_state(True)
        fake, _, error = self.execute(records, bootstrap=False, oauth_recovery=True, fingerprint="c" * 64)
        self.assertIsNotNone(error)
        self.assertFalse(fake.applied("ConfigMap"))
        fake, smoke, error = self.execute(records, bootstrap=False, oauth_recovery=True, smoke_error=True)
        self.assertIsNotNone(error)
        self.assertEqual(smoke, 1)
        receipts = {d["metadata"]["name"]: d for d in fake.applied("ConfigMap")}
        self.assertNotIn(deploy.release_name(SHA), receipts)
        receipt = receipts["fruition-bootstrap-oauth-recovery"]
        self.assertIsNone(self.execute(records + [receipt], bootstrap=False, oauth_recovery=True)[2])
        for field in ("original_manifest", "manifest", "fingerprints", "sha", "config"):
            bad = copy.deepcopy(receipt)
            bad["data"][field] = "tampered"
            fake, _, error = self.execute(records + [bad], bootstrap=False)
            self.assertIsNotNone(error, field)
            self.assertFalse(fake.applied("Deployment"))
        bad = copy.deepcopy(receipt)
        bad["immutable"] = False
        self.assertIsNotNone(self.execute(records + [bad], bootstrap=False)[2])

    def test_oauth_promotion_rejects_wrong_lifecycle_or_changed_readiness_chain(self):
        cases = [[], self.pre_oauth_state()[:1], self.state(True),
                 self.pre_oauth_state() + [{"metadata": {"name": deploy.release_name(SHA)}}]]
        for records in cases:
            fake, _, error = self.execute(records, bootstrap=False, oauth_recovery=True)
            self.assertIsNotNone(error)
            self.assertFalse(fake.applied("ConfigMap"))
        records = self.pre_oauth_state(True)
        self.assertIsNotNone(self.execute(records, oauth_recovery=True)[2])
        for option in ("probe_recovery", "mail_health_recovery"):
            self.assertIsNotNone(self.execute(records, bootstrap=False, oauth_recovery=True, **{option: True})[2])
        for index, key, value in ((0, "sha", "c" * 40), (1, "manifest", "changed"),
                                  (2, "original_manifest", "changed"), (3, "manifest", "changed")):
            changed = copy.deepcopy(records)
            changed[index]["data"][key] = value
            self.assertIsNotNone(self.execute(changed, bootstrap=False, oauth_recovery=True)[2])
        for review, rollback in ((REVIEW, False), (None, True)):
            with self.assertRaisesRegex(ValueError, "OAuth 복구"):
                deploy.deploy(CONFIG, SHA, self.documents, review=review, rollback=rollback, oauth_recovery=True)

    def test_oauth_matcher_rejects_arbitrary_or_partial_secret_and_workload_changes(self):
        records = self.pre_oauth_state()
        before = records[0]["data"]["manifest"]
        self.assertTrue(deploy.access_oauth_secret_recovery(before, self.documents))
        for field in ("missing", "duplicate", "remote_key", "property", "version", "other_secret", "image", "target"):
            changed = copy.deepcopy(self.documents)
            secret = next(d for d in changed if d["kind"] == "ExternalSecret" and d["metadata"]["name"] == "fruition-access")
            entry = next(e for e in secret["spec"]["data"] if e["secretKey"] == "GOOGLE_CLIENT_ID")
            if field == "missing": secret["spec"]["data"].remove(entry)
            elif field == "duplicate": secret["spec"]["data"].append(copy.deepcopy(entry))
            elif field == "remote_key": entry["remoteRef"]["key"] = "other/app"
            elif field == "property": entry["remoteRef"]["property"] = "JWT_SECRET"
            elif field == "version": entry["remoteRef"]["version"] = "other"
            elif field == "target": secret["spec"]["target"]["name"] = "other"
            elif field == "other_secret": secret["spec"]["data"][0]["remoteRef"]["property"] = "other"
            else:
                next(d for d in changed if d["kind"] == "Deployment")["spec"]["template"]["spec"]["containers"][0]["image"] = "different:" + SHA
            self.assertFalse(deploy.access_oauth_secret_recovery(before, changed), field)
        self.assertFalse(deploy.access_oauth_secret_recovery("invalid", self.documents))
        self.assertFalse(deploy.access_oauth_secret_recovery("[invalid", self.documents))

    def test_workflow_wires_explicit_oauth_recovery_input(self):
        workflow = (ROOT / ".github/workflows/deploy.yml").read_text()
        self.assertIn("bootstrap_oauth_recovery:", workflow)
        self.assertIn("BOOTSTRAP_OAUTH_RECOVERY: ${{ inputs.bootstrap_oauth_recovery }}", workflow)
        self.assertIn('if [ "$BOOTSTRAP_OAUTH_RECOVERY" = true ]; then EXTRA+=(--bootstrap-oauth-recovery); fi', workflow)


if __name__ == "__main__":
    unittest.main()
