"""External EKS sleep/wake controller. No HTTP endpoint or request replay.

One reserved Lambda concurrency serializes operator commands and scheduled ticks.
Persist intent before AWS mutations so the next tick can recover partial updates.
"""

import json
import os
import time
from datetime import datetime, timezone


class Controller:
    def __init__(self, eks, scaling, metrics, table, cluster, groups, alb, now=None):
        self.eks = eks
        self.scaling = scaling
        self.metrics = metrics
        self.table = table
        self.cluster = cluster
        self.groups = groups
        self.alb = alb
        self.now = int(time.time() if now is None else now)

    def read(self):
        return self.table.get_item(Key={"id": "controller"}, ConsistentRead=True).get(
            "Item", {"id": "controller", "phase": "awake"}
        )

    def save(self, state, phase):
        state["phase"] = phase
        self.table.put_item(Item=state)

    def nodegroups(self):
        return {
            key: self.eks.describe_nodegroup(
                clusterName=self.cluster, nodegroupName=name
            )["nodegroup"]
            for key, name in self.groups.items()
        }

    def asg(self, node):
        names = [g["name"] for g in node["resources"]["autoScalingGroups"]]
        if len(names) != 1:
            raise RuntimeError("Expected one Auto Scaling group per managed node group")
        return self.scaling.describe_auto_scaling_groups(
            AutoScalingGroupNames=names
        )["AutoScalingGroups"][0]

    def has_request(self, state):
        # Retain the first partial minute: delayed datapoints must not lose the
        # only request. A pre-sleep error in that minute can cause a safe wake.
        start = int(state["since"]) // 60 * 60
        age = self.now - start
        unit = 3600 if age >= 63 * 86400 else 300 if age >= 15 * 86400 else 60
        period = max(unit, ((age // (unit * 1400)) + 1) * unit)
        result = self.metrics.get_metric_statistics(
            Namespace="AWS/ApplicationELB",
            MetricName="HTTPCode_ELB_5XX_Count",
            Dimensions=[{"Name": "LoadBalancer", "Value": self.alb}],
            StartTime=datetime.fromtimestamp(start, timezone.utc),
            EndTime=datetime.fromtimestamp(self.now + 1, timezone.utc),
            Period=period,
            Statistics=["Sum"],
        )
        return any(point.get("Sum", 0) > 0 for point in result["Datapoints"])

    def resize(self, key, node, desired):
        if node["status"] != "ACTIVE":
            return False
        config = node["scalingConfig"]
        # During wake retain any larger operator/autoscaler capacity.
        wanted = max(desired, config["desiredSize"]) if desired else 0
        minimum = 2 if desired else 0
        if config["desiredSize"] == wanted and config["minSize"] == minimum:
            return True
        self.eks.update_nodegroup_config(
            clusterName=self.cluster,
            nodegroupName=self.groups[key],
            scalingConfig={"minSize": minimum, "desiredSize": wanted},
        )
        return False

    def run(self, event):
        action = event.get("action", "")
        if action not in {"sleep", "wake", "tick", "status"}:
            raise ValueError("Expected sleep, wake, tick, or status")
        state = self.read()
        if action == "status":
            return state
        if action == "sleep":
            if event.get("confirm_no_active_jobs") is not True:
                raise ValueError("Confirm no active jobs before sleep")
            if state["phase"] == "waking":
                raise ValueError("Wait for wake to finish before sleeping")
            if state["phase"] == "awake":
                nodes = self.nodegroups()
                if any(n["status"] != "ACTIVE" for n in nodes.values()):
                    raise ValueError("Node groups must be ACTIVE before sleep")
                owned = []
                for node in nodes.values():
                    group = self.asg(node)
                    if any(p["ProcessName"] == "Launch" for p in group["SuspendedProcesses"]):
                        raise ValueError("Launch already suspended outside this controller")
                    owned.append(group["AutoScalingGroupName"])
                state = {"id": "controller", "since": self.now, "owned_asgs": owned}
                self.save(state, "sleeping")
        if action == "wake" and state["phase"] != "awake":
            self.save(state, "waking")
        if state["phase"] in {"sleeping", "asleep"} and action == "tick":
            if self.has_request(state):
                self.save(state, "waking")
        if state["phase"] == "awake":
            return state

        nodes = self.nodegroups()
        # Replacing a node group while asleep requires operator intervention;
        # never mutate a newly discovered ASG outside the persisted sleep intent.
        groups = {key: self.asg(node) for key, node in nodes.items()}
        if set(state["owned_asgs"]) != {g["AutoScalingGroupName"] for g in groups.values()}:
            raise RuntimeError("Node groups changed during sleep; inspect before recovery")

        if state["phase"] in {"sleeping", "asleep"}:
            # The in-cluster autoscaler may race a scale-to-zero operation. A
            # suspended Launch process prevents replacement instances appearing.
            for name in state["owned_asgs"]:
                self.scaling.suspend_processes(
                    AutoScalingGroupName=name, ScalingProcesses=["Launch"]
                )
            complete = True
            for key, node in nodes.items():
                if not self.resize(key, node, 0) or groups[key]["Instances"]:
                    complete = False
            if complete and state["phase"] != "asleep":
                self.save(state, "asleep")
        elif state["phase"] == "waking":
            # Restore Launch even if an EKS update is still in progress, so a
            # partially completed wake cannot leave capacity permanently stuck.
            for name in state["owned_asgs"]:
                self.scaling.resume_processes(
                    AutoScalingGroupName=name, ScalingProcesses=["Launch"]
                )
            ready = self.resize("general", nodes["general"], 2)
            running = sum(
                i["LifecycleState"] == "InService" for i in groups["general"]["Instances"]
            )
            if ready and running >= 2:
                self.save(state, "awake")
        return state


def handler(event, context):
    import boto3
    from botocore.config import Config

    config = Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2})
    controller = Controller(
        boto3.client("eks", config=config),
        boto3.client("autoscaling", config=config),
        boto3.client("cloudwatch", config=config),
        boto3.resource("dynamodb", config=config).Table(os.environ["STATE_TABLE"]),
        os.environ["CLUSTER_NAME"],
        json.loads(os.environ["NODE_GROUPS"]),
        os.environ["ALB_SUFFIX"],
    )
    result = controller.run(event)
    print(json.dumps({"action": event.get("action"), "phase": result["phase"]}))
    # DynamoDB returns Decimal timestamps; return only an API-safe summary.
    return {"phase": result["phase"], "since": int(result.get("since", 0))}
