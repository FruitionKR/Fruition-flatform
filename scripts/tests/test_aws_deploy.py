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


if __name__ == "__main__":
    unittest.main()
