"""실제 렌더의 IAM·TLS·NetworkPolicy 합집합과 배포 순서를 검사한다."""

import ipaddress
import json
import re
import subprocess
import unittest
from unittest.mock import patch

from test_aws_deploy import CONFIG, SHA, MANIFEST, REVIEW, FakeCluster, deploy


def selected(selector, app):
    labels = {"app": app}
    return all(labels.get(k) == v for k,v in selector.get("matchLabels", {}).items()) and all(
        (labels.get(e["key"]) in e["values"]) == (e["operator"] == "In")
        for e in selector.get("matchExpressions", []))


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("smoke_settings", {"test": "fixture"}), ("authenticated_smoke", None)):
            mock = patch.object(deploy, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    @classmethod
    def setUpClass(cls):
        cls.docs=deploy.render(CONFIG,SHA,MANIFEST)
        cls.policies=[d for d in cls.docs if d["kind"]=="NetworkPolicy"]

    def allows(self, app, direction, port, other_app=None, ip=None):
        for policy in self.policies:
            spec=policy["spec"]
            if not selected(spec["podSelector"],app): continue
            for rule in spec.get(direction,[]):
                if port not in [p["port"] for p in rule.get("ports",[])]:continue
                for peer in rule.get("from" if direction=="ingress" else "to",[]):
                    if other_app and "podSelector" in peer and "namespaceSelector" not in peer and selected(peer["podSelector"],other_app):return True
                    if ip and "ipBlock" in peer:
                        block=peer["ipBlock"];address=ipaddress.ip_address(ip)
                        if address in ipaddress.ip_network(block["cidr"]) and not any(address in ipaddress.ip_network(c) for c in block.get("except",[])):return True
        return False

    def test_effective_internal_ingress_and_metadata_denials(self):
        self.assertNotIn("internal-only-ingress",[d["metadata"]["name"] for d in self.policies])
        for src,dst,port in [("access-svc","document-svc",8080),("document-svc","access-svc",8081),
                             ("document-svc","pipeline-api",8000),("ingest-worker","document-svc",8080),
                             ("pipeline-api","access-svc",8081)]:
            self.assertTrue(self.allows(src,"egress",port,other_app=dst))
            self.assertTrue(self.allows(dst,"ingress",port,other_app=src))
        # converter는 Kafka worker라 어떤 pod의 ingress도 받지 않고 document가 HTTP로 부르지도 않는다.
        for src in ("document-svc","pipeline-api","ingest-worker"):
            self.assertFalse(self.allows("converter","ingress",8000,other_app=src))
            self.assertFalse(self.allows(src,"egress",8000,other_app="converter"))
        # converter는 사용량 원장(ai_model_usage)·작업 journal 기록을 위해 전용 계정으로 RDS에 접속한다.
        self.assertTrue(self.allows("converter","egress",5432,ip="10.0.5.5"))
        self.assertTrue(any(selected(p["spec"]["podSelector"],"converter") for p in self.policies if p["metadata"]["name"]=="aws-app-kafka"))
        self.assertTrue(self.allows("converter","egress",443,ip="52.1.2.3"))
        self.assertFalse(self.allows("converter","egress",6379,ip="10.0.5.5"))
        self.assertFalse(self.allows("ingest-worker","egress",443,ip="169.254.169.254"))
        self.assertFalse(self.allows("ingest-worker","egress",443,ip="10.0.5.5"))
        self.assertTrue(self.allows("ingest-worker","egress",443,ip="52.1.2.3"))
        for app in ("access-svc","document-svc"):
            self.assertTrue(self.allows(app,"ingress",8082,ip="10.0.101.5"))
            self.assertFalse(self.allows(app,"ingress",8082,ip="10.0.50.5"))

    def test_jobs_receive_dns_and_database_before_first_preflight(self):
        fake=FakeCluster()
        with patch.object(deploy,"run",fake.run):deploy.deploy(CONFIG,SHA,self.docs,review=REVIEW)
        first_job=next(i for i,(_,ds) in enumerate(fake.events) if any(d["kind"]=="Job" for d in ds))
        self.assertTrue(any(any(d["kind"]=="NetworkPolicy" for d in ds) for _,ds in fake.events[:first_job]))
        for svc in ("access","document","ai"):
            for kind in ("migration","db-preflight"):
                app=f"{svc}-{kind}"
                self.assertTrue(self.allows(app,"egress",5432,ip="10.0.5.5"))
                self.assertFalse(self.allows(app,"egress",6379,ip="10.0.5.5"))
                self.assertFalse(self.allows(app,"egress",443,ip="52.1.2.3"))
        jobs=[d for d in self.docs if d["kind"]=="Job"]
        for job in jobs:
            self.assertIn({"name":"PGSSLMODE","value":"require"},job["spec"]["template"]["spec"]["containers"][0]["env"])

    def test_upgrade_removes_existing_broad_policy_after_restrictive_apply(self):
        fake=FakeCluster()
        self.assertIn("internal-only-ingress",fake.policies)
        with patch.object(deploy,"run",fake.run):deploy.deploy(CONFIG,SHA,self.docs,review=REVIEW)
        self.assertNotIn("internal-only-ingress",fake.policies)
        deletion=next(i for i,(args,_) in enumerate(fake.events) if args[3:6]==["delete","networkpolicy","internal-only-ingress"])
        self.assertTrue(any(any(d["kind"]=="NetworkPolicy" and d["metadata"]["name"]=="aws-app-default-deny" for d in ds) for _,ds in fake.events[:deletion]))
        self.assertFalse(any(any(d["kind"]=="Job" for d in ds) for _,ds in fake.events[:deletion]))
        failed=FakeCluster(fail="internal-only-ingress")
        with patch.object(deploy,"run",failed.run),self.assertRaises(subprocess.CalledProcessError):
            deploy.deploy(CONFIG,SHA,self.docs,review=REVIEW)
        self.assertIn("internal-only-ingress",failed.policies)
        self.assertFalse(failed.applied("Job"));self.assertFalse(failed.applied("Deployment"))

    def test_irsa_secrets_and_smtp_have_single_authority(self):
        accounts={d["metadata"]["name"]:d for d in self.docs if d["kind"]=="ServiceAccount"}
        for service in ("document","pipeline","converter"):
            self.assertEqual(CONFIG[f"{service}_storage_role_arn"],accounts[f"fruition-{service}"]["metadata"]["annotations"]["eks.amazonaws.com/role-arn"])
        # 화면은 기동 요청 이벤트 발행·상태 조회만 하는 전용 role을 쓴다.
        self.assertEqual(f"arn:aws:iam::{CONFIG['account_id']}:role/fruition-frontend-wake",
                         accounts["fruition-frontend"]["metadata"]["annotations"]["eks.amazonaws.com/role-arn"])
        for name,account in accounts.items():
            if name not in {"fruition-document","fruition-pipeline","fruition-converter","fruition-frontend"}:self.assertNotIn("eks.amazonaws.com/role-arn",account["metadata"].get("annotations",{}))
        secrets=[d for d in self.docs if d["kind"]=="ExternalSecret"]
        self.assertNotIn("S3_ACCESS_KEY",json.dumps(secrets));self.assertNotIn("S3_SECRET_KEY",json.dumps(secrets))
        self.assertNotIn("SPRING_MAIL_PORT",json.dumps(secrets))
        config=next(d["data"] for d in self.docs if d["kind"]=="ConfigMap")
        self.assertEqual("require",config["PGSSLMODE"]);self.assertEqual("true",config["REDIS_SSL"])
        self.assertEqual("aws",config["S3_CREDENTIALS_MODE"])
        self.assertTrue(self.allows("access-svc","egress",int(config["SPRING_MAIL_PORT"]),ip="52.1.2.3"))
        for key,value in [("smtp_port","0587"),("alb_subnet_cidr_1",CONFIG["vpc_cidr"]),
                          ("alb_subnet_cidr_2",CONFIG["alb_subnet_cidr_1"]),
                          ("pipeline_storage_role_arn",CONFIG["document_storage_role_arn"]),
                          ("converter_storage_role_arn",CONFIG["pipeline_storage_role_arn"])]:
            with self.assertRaises(ValueError):deploy.validate({**CONFIG,key:value},SHA)

    def test_storage_policy_preserves_domain_and_rollback_boundaries(self):
        source=(deploy.ROOT / "infra/terraform/s3.tf").read_text()
        scopes={}
        for service in ("document","pipeline","converter"):
            block=re.search(rf'{service}\s*=\s*\{{(.*?)\n\s*\}}',source,re.S).group(1)
            scopes[service]={action:json.loads(re.search(rf'{action}\s*=\s*(\[[^\]]*\])',block).group(1)) for action in ("read","write","delete")}
        self.assertEqual(["sources/documents/*","assets/*","tmp/document-uploads/*","meetings/*"],scopes["document"]["write"])
        self.assertEqual(["sources/documents/*", "assets/*", "meetings/*"], scopes["document"]["delete"])
        self.assertIn("tmp/document-uploads/*", scopes["document"]["read"])
        self.assertIn('"s3:ListMultipartUploadParts"', source)
        self.assertIn('"s3:GetObjectVersion"', source)
        self.assertIn("wiki/*",scopes["document"]["read"])
        self.assertIn("meetings/*",scopes["document"]["read"])
        self.assertIn("sources/documents/*",scopes["pipeline"]["read"])
        self.assertEqual(["wiki/*","agent-runs/*"],scopes["pipeline"]["delete"])
        # converter(ai ADR 0034)는 원본 읽기와 변환 결과 쓰기만 하고, document는 그 결과를 읽는다.
        self.assertEqual({"read":["sources/documents/*"],"write":["tmp/convert/*"],"delete":[]},scopes["converter"])
        self.assertIn("tmp/convert/*",scopes["document"]["read"])
        self.assertRegex(re.sub(r"\s+"," ",source),r'prefix = "tmp/convert/" } expiration \{ days = 1 \}')
        self.assertIn("pipeline-runs/*",scopes["pipeline"]["write"])
        self.assertNotIn("pipeline-runs/*",scopes["pipeline"]["delete"])
        self.assertNotIn('resource "aws_iam_access_key"',source)
        self.assertNotIn('resource "aws_iam_user"',source)
        self.assertIn('"s3:AbortMultipartUpload"',source)
        self.assertIn('"s3:ListBucket"',source)


if __name__=="__main__":unittest.main()
