"""형제 Document·AI checkout과 플랫폼 ACL의 통합 계약. 명시적으로 실행한다."""
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import test_aws_redis_acl as acl

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT.parent / "AI/pipeline"))
from app.modules.wiki_ingestion.infrastructure import workspace_concept_lock

class ServiceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.redis = acl.RedisAclTest
        cls.redis.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.redis.tearDownClass()

    def test_document_acl_matches_service_contract(self):
        text = (ROOT / "infra/terraform/elasticache.tf").read_text()
        acl = re.search(r'^\s*document\s*=\s*"([^"]+)"', text, re.M).group(1)
        self.assertEqual(acl, (ROOT.parent / "Document/src/test/resources/redis-document.acl").read_text().strip())

    def test_ai_adapter_uses_own_credentials(self):
        with patch.dict(os.environ, {"REDIS_HOST":"127.0.0.1", "REDIS_PORT":str(self.redis.port),
                                    "REDIS_USERNAME":"pipeline", "REDIS_PASSWORD":self.redis.ai_password}, clear=True):
            workspace_concept_lock._client.cache_clear()
            workspace_concept_lock.put_concept_index("u","w",[{"id":"c"}])
            self.assertEqual([{"id":"c"}], workspace_concept_lock.get_concept_index("u","w"))
            workspace_concept_lock.invalidate_concept_index("u","w")
            self.assertIsNone(workspace_concept_lock.get_concept_index("u","w"))
            workspace_concept_lock._client().close(); workspace_concept_lock._client.cache_clear()

