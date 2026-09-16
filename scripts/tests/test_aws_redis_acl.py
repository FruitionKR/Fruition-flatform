"""임시 Redis 7.0에서 ElastiCache 7.1 호환 ACL·실제 redis-py를 검사한다."""

import re
import subprocess
import time
import unittest
import uuid
from pathlib import Path

import redis

ROOT = Path(__file__).resolve().parents[2]


def docker(*args):
    return subprocess.run(["docker", *args], text=True, capture_output=True, check=True).stdout.strip()


class RedisAclTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.name = "fruition-acl-test-" + uuid.uuid4().hex[:12]
        docker("run", "-d", "--rm", "--name", cls.name, "-p", "127.0.0.1::6379", "redis:7.0-alpine")
        try:
            port = int(docker("port", cls.name, "6379/tcp").rsplit(":", 1)[1])
            cls.port = port
            admin = redis.Redis(host="127.0.0.1", port=port, decode_responses=True)
            for _ in range(100):
                try:
                    if admin.ping(): break
                except redis.ConnectionError: time.sleep(.05)
            # 운영 Terraform의 access string 자체를 적용해 지원하지 않는 명령도 검출한다.
            text = (ROOT / "infra/terraform/elasticache.tf").read_text()
            cls.clients = {}
            for service, acl in re.findall(r'^\s*(access|document|pipeline)\s*=\s*"([^"]+)"', text, re.M):
                password = uuid.uuid4().hex
                admin.execute_command("ACL", "SETUSER", service, ">" + password, *acl.split())
                cls.clients[service] = redis.Redis(host="127.0.0.1", port=port, username=service,
                                                   password=password, decode_responses=True)
                if service == "pipeline": cls.ai_password = password
            admin.execute_command("ACL", "SETUSER", "default", "off", "-@all")
        except BaseException:
            docker("rm", "-f", cls.name)
            raise

    @classmethod
    def tearDownClass(cls):
        for client in cls.clients.values(): client.close()
        docker("rm", "-f", cls.name)


    def test_real_commands_lua_pubsub_and_projection(self):
        access, doc = self.clients["access"], self.clients["document"]
        script = "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],300) end; return redis.call('TTL',KEYS[1])"
        self.assertGreater(access.eval(script, 1, "auth:mfa:attempts:u"), 0)
        access.set("oauth:exchange:code", "user", ex=60)
        self.assertEqual("user", access.getdel("oauth:exchange:code"))
        doc.set("authz:role:w:u", "EDITOR", ex=300)
        self.assertEqual("EDITOR", doc.get("authz:role:w:u"))
        self.assertEqual(1, access.delete("authz:role:w:u"))
        doc.set("query:run:q", "running", nx=True, ex=60)
        self.assertEqual("running", doc.get("query:run:q"))
        doc.execute_command("INCR", "query:events-seq:q"); doc.pexpire("query:events-seq:q", 60000)
        relay = doc.pubsub(); relay.subscribe("query-events"); relay.get_message(timeout=1)
        lua = "redis.call('RPUSH',KEYS[1],ARGV[1]); redis.call('LTRIM',KEYS[1],-200,-1); redis.call('EXPIRE',KEYS[1],60); return redis.call('PUBLISH',ARGV[2],ARGV[1])"
        self.assertGreaterEqual(doc.eval(lua, 1, "query:events:q", "event", "query-events"), 1)
        self.assertEqual(["event"], doc.lrange("query:events:q",0,-1))
        self.assertEqual("event", relay.get_message(timeout=1)["data"])
        relay.unsubscribe(); relay.close()


    def test_denials_and_scan_metadata_exception(self):
        access, doc, ai = (self.clients[x] for x in ("access","document","pipeline"))
        for client,key in [(access,"query:run:private"),(doc,"oauth:exchange:private"),(ai,"authz:role:private")]:
            for command in (lambda:client.get(key),lambda:client.set(key,"x"),lambda:client.delete(key)):
                with self.assertRaises(redis.ResponseError): command()
            with self.assertRaises(redis.ResponseError): client.publish("other-channel","x")
            with self.assertRaises(redis.ResponseError): client.execute_command("SUBSCRIBE", "other-channel")
            with self.assertRaises(redis.ResponseError): client.flushdb()
        with self.assertRaises(redis.ResponseError): access.set("authz:role:w:u","ADMIN")
        with self.assertRaises(redis.ResponseError): access.get("authz:role:w:u")
        doc.set("query:run:metadata-visible", "secret")
        self.assertIn("query:run:metadata-visible", list(access.scan_iter()))
        anonymous=redis.Redis(host="127.0.0.1",port=self.port)
        with self.assertRaises(redis.AuthenticationError): anonymous.ping()
        anonymous.close()


if __name__ == "__main__": unittest.main()
