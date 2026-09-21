"""Exercise lifecycle behavior without AWS credentials or boto3 installation."""

import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import Mock


PATH = Path(__file__).resolve().parents[2] / "infra/lambda/request_wake/handler.py"
SPEC = importlib.util.spec_from_file_location("request_wake", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WakeTests(unittest.TestCase):
    def setUp(self):
        self.item = None
        self.table = Mock()
        self.table.get_item.side_effect = lambda **kw: (
            {"Item": copy.deepcopy(self.item)} if self.item else {}
        )
        self.table.put_item.side_effect = self.put
        self.nodes = {}
        self.groups = {}
        for key, desired in (("general", 2), ("ai_worker", 0)):
            self.nodes[key] = {
                "status": "ACTIVE",
                "scalingConfig": {"minSize": desired, "desiredSize": desired, "maxSize": 4},
                "resources": {"autoScalingGroups": [{"name": key + "-asg"}]},
            }
            self.groups[key + "-asg"] = {
                "AutoScalingGroupName": key + "-asg",
                "SuspendedProcesses": [],
                "Instances": [{"LifecycleState": "InService"}] * desired,
            }
        self.eks, self.scaling, self.metrics = Mock(), Mock(), Mock()
        self.eks.describe_nodegroup.side_effect = lambda **kw: {
            "nodegroup": copy.deepcopy(self.nodes[kw["nodegroupName"]])
        }
        self.eks.update_nodegroup_config.side_effect = self.update
        self.scaling.describe_auto_scaling_groups.side_effect = lambda **kw: {
            "AutoScalingGroups": [copy.deepcopy(self.groups[n]) for n in kw["AutoScalingGroupNames"]]
        }
        self.metrics.get_metric_statistics.return_value = {"Datapoints": []}
        self.controller = MODULE.Controller(
            self.eks, self.scaling, self.metrics, self.table, "cluster",
            {k: k for k in self.nodes}, "app/example/abc", now=1800000000,
        )

    def put(self, **kwargs):
        self.item = copy.deepcopy(kwargs["Item"])

    def update(self, **kwargs):
        node = self.nodes[kwargs["nodegroupName"]]
        node["scalingConfig"].update(kwargs["scalingConfig"])
        node["status"] = "UPDATING"

    def tick(self):
        return self.controller.run({"action": "tick"})

    def sleep(self):
        return self.controller.run({"action": "sleep", "confirm_no_active_jobs": True})

    def finish_updates(self):
        for key, node in self.nodes.items():
            node["status"] = "ACTIVE"
            self.groups[key + "-asg"]["Instances"] = (
                [{"LifecycleState": "InService"}] * node["scalingConfig"]["desiredSize"]
            )

    def test_awake_tick_does_not_change_capacity_or_query_metrics(self):
        self.assertEqual("awake", self.tick()["phase"])
        self.eks.update_nodegroup_config.assert_not_called()
        self.metrics.get_metric_statistics.assert_not_called()

    def test_sleep_requires_explicit_job_confirmation(self):
        with self.assertRaises(ValueError):
            self.controller.run({"action": "sleep"})
        self.table.put_item.assert_not_called()
        self.scaling.suspend_processes.assert_not_called()

    def test_existing_external_launch_suspension_is_not_taken_over(self):
        self.groups["general-asg"]["SuspendedProcesses"] = [{"ProcessName": "Launch"}]
        with self.assertRaises(ValueError):
            self.sleep()
        self.table.put_item.assert_not_called()

    def test_sleep_then_request_wakes_two_nodes_and_resumes_both_groups(self):
        self.assertEqual("sleeping", self.sleep()["phase"])
        self.assertEqual(2, self.scaling.suspend_processes.call_count)
        self.finish_updates()
        self.assertEqual("asleep", self.tick()["phase"])
        self.metrics.get_metric_statistics.return_value = {"Datapoints": [{"Sum": 1}]}
        self.assertEqual("waking", self.tick()["phase"])
        self.assertEqual(2, self.nodes["general"]["scalingConfig"]["desiredSize"])
        self.assertEqual(2, self.nodes["general"]["scalingConfig"]["minSize"])
        self.assertEqual(2, self.scaling.resume_processes.call_count)
        self.finish_updates()
        self.assertEqual("awake", self.tick()["phase"])

    def test_sleep_does_not_finish_while_instances_are_still_terminating(self):
        self.sleep()
        self.nodes["general"]["status"] = "ACTIVE"
        self.assertEqual("sleeping", self.tick()["phase"])

    def test_request_during_scale_down_waits_for_eks_update_then_wakes(self):
        self.sleep()
        self.metrics.get_metric_statistics.return_value = {"Datapoints": [{"Sum": 1}]}
        self.eks.update_nodegroup_config.reset_mock()
        self.assertEqual("waking", self.tick()["phase"])
        self.eks.update_nodegroup_config.assert_not_called()
        self.finish_updates()
        self.tick()
        self.assertEqual(2, self.nodes["general"]["scalingConfig"]["desiredSize"])

    def test_failed_sleep_is_persisted_and_manual_wake_recovers(self):
        self.scaling.suspend_processes.side_effect = RuntimeError("partial failure")
        with self.assertRaises(RuntimeError):
            self.sleep()
        self.assertEqual("sleeping", self.item["phase"])
        self.controller.run({"action": "wake"})
        self.assertEqual("awake", self.item["phase"])
        self.assertEqual(2, self.scaling.resume_processes.call_count)

    def test_failed_wake_retries_without_losing_intent(self):
        self.sleep()
        self.finish_updates()
        self.scaling.resume_processes.side_effect = RuntimeError("temporary error")
        with self.assertRaises(RuntimeError):
            self.controller.run({"action": "wake"})
        self.assertEqual("waking", self.item["phase"])
        self.scaling.resume_processes.side_effect = None
        self.tick()
        self.assertEqual(2, self.nodes["general"]["scalingConfig"]["desiredSize"])

    def test_repeated_sleep_does_not_reset_request_detection_start(self):
        self.sleep()
        since = self.item["since"]
        self.controller.now += 120
        self.sleep()
        self.assertEqual(since, self.item["since"])

    def test_sleep_during_wake_is_rejected(self):
        self.sleep()
        self.controller.run({"action": "wake"})
        with self.assertRaises(ValueError):
            self.sleep()

    def test_duplicate_ticks_do_not_submit_conflicting_eks_updates(self):
        self.sleep()
        self.finish_updates()
        self.controller.run({"action": "wake"})
        self.eks.update_nodegroup_config.reset_mock()
        self.tick()
        self.tick()
        self.eks.update_nodegroup_config.assert_not_called()

    def test_wake_does_not_reduce_larger_capacity(self):
        self.sleep()
        self.finish_updates()
        self.nodes["general"]["scalingConfig"]["desiredSize"] = 4
        self.controller.run({"action": "wake"})
        self.assertEqual(4, self.nodes["general"]["scalingConfig"]["desiredSize"])

    def test_replaced_asg_is_not_mutated(self):
        self.sleep()
        self.nodes["general"]["resources"]["autoScalingGroups"][0]["name"] = "replacement"
        self.groups["replacement"] = dict(self.groups["general-asg"], AutoScalingGroupName="replacement")
        self.scaling.resume_processes.reset_mock()
        with self.assertRaises(RuntimeError):
            self.controller.run({"action": "wake"})
        self.scaling.resume_processes.assert_not_called()

    def test_status_is_read_only(self):
        self.sleep()
        self.eks.describe_nodegroup.reset_mock()
        self.assertEqual("sleeping", self.controller.run({"action": "status"})["phase"])
        self.eks.describe_nodegroup.assert_not_called()

    def test_single_delayed_request_is_included_and_long_sleep_uses_valid_period(self):
        self.sleep()
        self.controller.now += 70 * 86400
        self.tick()
        kwargs = self.metrics.get_metric_statistics.call_args.kwargs
        self.assertEqual(0, kwargs["Period"] % 3600)
        self.assertLessEqual((self.controller.now - self.item["since"]) / kwargs["Period"], 1440)
        self.assertLessEqual(kwargs["StartTime"].timestamp(), self.item["since"])


if __name__ == "__main__":
    unittest.main()
