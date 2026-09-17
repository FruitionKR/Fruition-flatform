"""Check the rendered Kafka transport/identity/ACL contract, not just patches."""
import unittest
from test_aws_deploy import CONFIG, SHA, deploy


class KafkaSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = deploy.render(CONFIG, SHA)
        cls.users = {d["metadata"]["name"]: d["spec"] for d in cls.docs if d["kind"] == "KafkaUser"}
        cls.apps = {d["metadata"]["name"]: d["spec"]["template"]["spec"] for d in cls.docs if d["kind"] == "Deployment"}

    def permits(self, user, kind, name, operation):
        return any(a["resource"]["type"] == kind and a["resource"].get("name") == name
                   and operation in a["operations"] for a in self.users[user]["authorization"]["acls"])

    def test_no_plain_listener_and_namespace_scoped_clients(self):
        kafka = next(d["spec"] for d in self.docs if d["kind"] == "Kafka")
        self.assertEqual("simple", kafka["kafka"]["authorization"]["type"])
        self.assertIn("userOperator", kafka["entityOperator"])
        listener, = kafka["kafka"]["listeners"]
        self.assertEqual(9093, listener["port"])
        self.assertTrue(listener["tls"])
        self.assertEqual({"type": "tls"}, listener["authentication"])
        peers = listener["networkPolicyPeers"]
        self.assertFalse(any(not p or p.get("namespaceSelector") == {} or p.get("podSelector") == {} for p in peers))
        self.assertEqual("keda", peers[-1]["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"])
        for spec in self.users.values():
            self.assertEqual({"type": "tls"}, spec["authentication"])
        pool = next(d for d in self.docs if d["kind"] == "KafkaNodePool")
        self.assertEqual(1, pool["spec"]["replicas"])

    def test_consumers_match_acl_group_and_no_unrelated_topic_write(self):
        groups = {"ingest-worker": "ai.ingest.command", "query-task-worker": "ai.query.command",
                  "agent-task-worker": "ai.agent.command", "maintenance-task-worker": "ai.maintenance.command"}
        for group, topic in groups.items():
            self.assertTrue(self.permits("kafka-"+group,"topic",topic,"Read"))
            self.assertTrue(self.permits("kafka-"+group,"group",group,"Read"))
            self.assertTrue(self.permits("kafka-"+group,"topic","ai.task.event","Write"))
            self.assertFalse(self.permits("kafka-"+group,"topic","document.edit.event","Write"))
        self.assertTrue(self.permits("kafka-ingest-worker","topic","ai.maintenance.command","Write"))
        self.assertTrue(self.permits("kafka-edit-event-consumer","group","derived-state-tracker","Read"))
        self.assertTrue(self.permits("kafka-document","group","document-svc-ai-task-result","Read"))
        self.assertFalse(any("Write" in a["operations"] or "Read" in a["operations"] for a in self.users["kafka-keda"]["authorization"]["acls"]))

    def test_each_client_mounts_own_identity_and_trust(self):
        names = ["document-svc","ingest-worker","query-task-worker","agent-task-worker","maintenance-task-worker","edit-event-consumer"]
        for name in names:
            spec = self.apps[name]
            env = {e["name"]:e for e in spec["containers"][0]["env"]}
            self.assertTrue(env["KAFKA_BOOTSTRAP_SERVERS"]["value"].endswith(":9093"))
            volumes = {v["name"]:v for v in spec["volumes"]}
            username = "document" if name == "document-svc" else name
            self.assertEqual("kafka-"+username,volumes["kafka-client"]["secret"]["secretName"])
            self.assertEqual("kafka-cluster-ca-cert",volumes["kafka-ca"]["secret"]["secretName"])
            key = "SPRING_KAFKA_SECURITY_PROTOCOL" if name == "document-svc" else "KAFKA_SECURITY_PROTOCOL"
            self.assertEqual("SSL",env[key]["value"])
        # Pipeline API/converter do not receive other clients' Kafka certificates.
        for name in ("access-svc","pipeline-api","converter"):
            self.assertNotIn("kafka-client",[v["name"] for v in self.apps[name].get("volumes",[])])

    def test_keda_uses_separate_read_only_identity(self):
        auth = next(d for d in self.docs if d["kind"] == "TriggerAuthentication")
        refs = {x["parameter"]:x for x in auth["spec"]["secretTargetRef"]}
        self.assertEqual("kafka-keda",refs["cert"]["name"])
        self.assertEqual("kafka-keda",refs["key"]["name"])
        for d in self.docs:
            if d["kind"] != "ScaledObject": continue
            trigger, = d["spec"]["triggers"]
            self.assertEqual("enable",trigger["metadata"]["tls"])
            self.assertTrue(trigger["metadata"]["bootstrapServers"].endswith(":9093"))
            self.assertEqual(auth["metadata"]["name"],trigger["authenticationRef"]["name"])
            self.assertTrue(self.permits("kafka-keda","group",trigger["metadata"]["consumerGroup"],"Describe"))


if __name__ == "__main__":
    unittest.main()
