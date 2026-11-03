"""Explicit offline migration gate. No reset, repair, automatic retry or audit deletion."""
import hashlib
import json
import re
import sys

import yaml

PREFIX = "fruition-maintenance-"
SERVICES = {"access", "document", "ai"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def validate_maintenance_review(review, sha):
    required = {"release_sha", "migration_mode", "expected_predecessor_release",
                "predecessor_record_sha256", "before_fingerprints", "after_fingerprints",
                "expected_live_images", "maintenance_test_url", "restore_test_url",
                "quiescence_test_url", "data_loss_accepted"}
    if set(review) != required or review["release_sha"] != sha:
        raise ValueError("maintenance review fields/release do not match")
    predecessor = review["expected_predecessor_release"]
    if not isinstance(predecessor, str) or not re.fullmatch(r"[0-9a-f]{40}", predecessor) or predecessor == sha:
        raise ValueError("maintenance requires a distinct predecessor release")
    if review["data_loss_accepted"] is not True:
        raise ValueError("maintenance requires the explicitly reviewed data-loss acceptance")
    for values in (review["before_fingerprints"], review["after_fingerprints"]):
        if not isinstance(values, dict) or set(values) != SERVICES or any(
                not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{64}", v) for v in values.values()):
            raise ValueError("maintenance requires all three schema fingerprints")
    if not isinstance(review["predecessor_record_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", review["predecessor_record_sha256"]):
        raise ValueError("maintenance requires the preserved predecessor record digest")
    images = review["expected_live_images"]
    if not isinstance(images, dict) or not images or any(
            not isinstance(k, str) or not re.fullmatch(r"[a-z0-9-]+/[a-z0-9-]+", k)
            or not isinstance(v, str) or not re.fullmatch(r"[a-zA-Z0-9./:_-]+@sha256:[0-9a-f]{64}", v)
            for k, v in images.items()):
        raise ValueError("maintenance requires exact live deployment/container digest references")
    for key in ("maintenance_test_url", "restore_test_url", "quiescence_test_url"):
        if not isinstance(review[key], str) or not re.fullmatch(
                r"https://github\.com/FruitionKR/[A-Za-z0-9_.-]+/(actions/runs/[0-9]+|issues/[0-9]+|pull/[0-9]+)(?:#[A-Za-z0-9_-]+)?", review[key]):
            raise ValueError("maintenance requires real reviewed evidence URLs: " + key)


def items(api, resource):
    return json.loads(api.kubectl("get", resource, "-o", "json"))["items"]


CLUSTER_OPERATOR = "strimzi-cluster-operator"
CLUSTER_OPERATOR_ENV_NAMES = set("""STRIMZI_NAMESPACE STRIMZI_FULL_RECONCILIATION_INTERVAL_MS
STRIMZI_OPERATION_TIMEOUT_MS STRIMZI_DEFAULT_KAFKA_EXPORTER_IMAGE
STRIMZI_DEFAULT_CRUISE_CONTROL_IMAGE STRIMZI_KAFKA_IMAGES STRIMZI_KAFKA_CONNECT_IMAGES
STRIMZI_KAFKA_MIRROR_MAKER_2_IMAGES STRIMZI_DEFAULT_TOPIC_OPERATOR_IMAGE
STRIMZI_DEFAULT_USER_OPERATOR_IMAGE STRIMZI_DEFAULT_KAFKA_INIT_IMAGE
STRIMZI_DEFAULT_KAFKA_BRIDGE_IMAGE STRIMZI_DEFAULT_KANIKO_EXECUTOR_IMAGE
STRIMZI_DEFAULT_BUILDAH_IMAGE STRIMZI_DEFAULT_MAVEN_BUILDER STRIMZI_OPERATOR_NAMESPACE
STRIMZI_FEATURE_GATES STRIMZI_LEADER_ELECTION_ENABLED STRIMZI_LEADER_ELECTION_LEASE_NAME
STRIMZI_LEADER_ELECTION_LEASE_NAMESPACE STRIMZI_LEADER_ELECTION_IDENTITY""".split())


def cluster_operator_pod(metadata, spec):
    """Recognize only the reviewed Strimzi runtime, never a label-only exemption."""
    labels = metadata.get("labels", {})
    containers = spec.get("containers", [])
    return (labels.get("name") == CLUSTER_OPERATOR
            and labels.get("strimzi.io/kind") == "cluster-operator"
            and spec.get("serviceAccountName") == CLUSTER_OPERATOR
            and not spec.get("initContainers") and not spec.get("ephemeralContainers")
            and len(containers) == 1
            and containers[0].get("name") == CLUSTER_OPERATOR
            and containers[0].get("image") == "quay.io/strimzi/operator:1.1.0"
            # Helm supplies the launcher as args to the image entrypoint.
            # Keep the reviewed default/explicit-command forms; never mix them.
            and (containers[0].get("command", []), containers[0].get("args", [])) in (
                ([], []),
                (["/opt/strimzi/bin/cluster_operator_run.sh"], []),
                ([], ["/opt/strimzi/bin/cluster_operator_run.sh"]))
            and not containers[0].get("envFrom")
            and all(e.get("name") in CLUSTER_OPERATOR_ENV_NAMES for e in containers[0].get("env", [])))


def cluster_operator_deployment(deployment):
    metadata = deployment["metadata"]
    labels = metadata.get("labels", {})
    template = deployment.get("spec", {}).get("template", {})
    return (metadata.get("name") == CLUSTER_OPERATOR
            and all(labels.get(k) == v for k, v in {
                "app": "strimzi", "app.kubernetes.io/managed-by": "Helm",
                "chart": "strimzi-kafka-operator-1.1.0", "component": "deployment",
                "heritage": "Helm", "release": "strimzi"}.items())
            and cluster_operator_pod(template.get("metadata", {}), template.get("spec", {})))


def assert_quiescent(api, documents):
    expected = {d["metadata"]["name"] for d in documents if d["kind"] == "Deployment"}
    deployments = items(api, "deployments")
    # Both reviewed Strimzi controllers are Kafka infrastructure, not app DB writers.
    cluster_operator_present = any(cluster_operator_deployment(d) for d in deployments)
    deployments = [d for d in deployments if not cluster_operator_deployment(d) and not (
        d["metadata"]["name"] == "kafka-entity-operator"
        and d["metadata"].get("labels", {}).get("strimzi.io/cluster") == "kafka"
        and d["metadata"].get("labels", {}).get("strimzi.io/kind") == "Kafka")]

    if {d["metadata"]["name"] for d in deployments} != expected:
        raise ValueError("maintenance workload inventory differs; review every writer")
    for d in deployments:
        if (d["spec"].get("replicas", 1) != 0 or d.get("status", {}).get("replicas", 0) != 0
                or d.get("status", {}).get("observedGeneration", 0) < d["metadata"]["generation"]):
            raise ValueError("maintenance requires observed zero replicas for every deployment")
    if items(api, "horizontalpodautoscalers"):
        raise ValueError("maintenance requires HPAs removed, including KEDA generated HPAs")
    if items(api, "scaledobjects"):
        raise ValueError("maintenance requires ScaledObjects removed after saving their manifests")
    if items(api, "cronjobs"):
        raise ValueError("maintenance requires no namespace CronJobs")
    for pod in items(api, "pods"):
        if pod.get("status", {}).get("phase") in {"Succeeded", "Failed"}:
            continue
        # The only persistent non-application workload in this namespace is Strimzi Kafka.
        labels = pod["metadata"].get("labels", {})
        if (labels.get("strimzi.io/cluster") == "kafka"
                and labels.get("strimzi.io/kind") == "Kafka"
                and any(o.get("kind") == "StrimziPodSet" for o in pod["metadata"].get("ownerReferences", []))):
            continue
        if (labels.get("strimzi.io/cluster") == "kafka"
                and labels.get("strimzi.io/name") == "kafka-entity-operator"
                and any(o.get("kind") == "ReplicaSet" and o.get("name", "").startswith("kafka-entity-operator-")
                        for o in pod["metadata"].get("ownerReferences", []))):
            continue
        owners = pod["metadata"].get("ownerReferences", [])
        if (cluster_operator_present
                and re.fullmatch(CLUSTER_OPERATOR + r"-[a-z0-9]+-[a-z0-9]+", pod["metadata"].get("name", ""))
                and cluster_operator_pod(pod["metadata"], pod.get("spec", {}))
                and len(owners) == 1 and owners[0].get("kind") == "ReplicaSet"
                and owners[0].get("controller") is True
                and re.fullmatch(CLUSTER_OPERATOR + r"-[a-z0-9]+", owners[0].get("name", ""))
                and pod["metadata"]["name"].startswith(owners[0]["name"] + "-")):
            continue
        raise ValueError("maintenance requires all application/Job Pods terminated")
    for job in items(api, "jobs"):
        if job.get("status", {}).get("active", 0):
            raise ValueError("maintenance requires no active jobs")
    return deployments


def maintenance_routes(api):
    routes = items(api, "ingresses")
    if not routes:
        raise ValueError("maintenance ingress evidence missing")
    for ingress in routes:
        annotation = ingress["metadata"].get("annotations", {}).get("alb.ingress.kubernetes.io/actions.maintenance", "{}")
        action = json.loads(annotation)
        if action != {"type": "fixed-response", "fixedResponseConfig": {
                "contentType": "text/plain", "statusCode": "503", "messageBody": "Maintenance"}}:
            raise ValueError("maintenance ingress must return the reviewed fixed 503 response")
        spec = ingress["spec"]
        backends = [p["backend"] for r in spec.get("rules", []) for p in r.get("http", {}).get("paths", [])]
        if "defaultBackend" in spec:
            backends.append(spec["defaultBackend"])
        if not backends or any(b != {"service": {"name": "maintenance", "port": {"name": "use-annotation"}}} for b in backends):
            raise ValueError("every ingress backend must be under maintenance")
    return [{"apiVersion": r["apiVersion"], "kind": "Ingress",
             "metadata": {k: v for k, v in r["metadata"].items() if k in {"name", "namespace", "labels", "annotations"}},
             "spec": r["spec"]} for r in routes]


def create_record(api, name, data):
    # create, not apply: a concurrent or interrupted attempt must never overwrite the lock.
    api.kubectl("create", "-f", "-", input=yaml.safe_dump(api.install_record(name, data)))


def complete_migrated_release(api, config, sha, documents, *, review, plan, images=None):
    """Explicit reviewed forward completion; no migration, rollback, or audit rewrite."""
    settings = api.validate_deploy_inputs(config, sha, documents, review=review, images=images)
    if review["migration_mode"] != "maintenance-cutover":
        raise ValueError("recovery requires the original maintenance review")
    required = {"release_sha", "mode", "started_data_sha256", "failed_data_sha256", "incident_url"}
    if (not isinstance(plan, dict) or set(plan) != required or plan["release_sha"] != sha
            or plan["mode"] != "complete-after-migrations"
            or any(not isinstance(plan[k], str) or not re.fullmatch(r"[0-9a-f]{64}", plan[k])
                   for k in ("started_data_sha256", "failed_data_sha256"))
            or not isinstance(plan["incident_url"], str)
            or not re.fullmatch(r"https://github\.com/FruitionKR/Fruition-flatform/actions/runs/[0-9]+", plan["incident_url"])):
        raise ValueError("invalid reviewed forward-completion plan")
    api.verify_target(config)
    api.verify_alb_log_destination(config)
    records = {r["metadata"]["name"]: r for r in items(api, "configmaps")}
    prefix = PREFIX + sha
    if api.release_name(sha) in records or prefix + "-recovery-started" in records:
        raise ValueError("recovery cannot repeat or overwrite a completed release")
    for name in records:
        if name.startswith(PREFIX) and name.endswith("-started") and name != prefix + "-started":
            other = name[len(PREFIX):-len("-started")]
            if api.release_name(other) not in records:
                raise ValueError("another unresolved maintenance attempt exists")
    for suffix, key in (("-started", "started_data_sha256"), ("-failed", "failed_data_sha256")):
        record = records.get(prefix + suffix, {})
        if record.get("immutable") is not True or digest(record.get("data", {})) != plan[key]:
            raise ValueError("recovery audit does not match the reviewed incident")
    started = records[prefix + "-started"]["data"]
    if (json.loads(started["config"]) != config or json.loads(started["review"]) != review
            or list(yaml.safe_load_all(started["manifest"])) != documents):
        raise ValueError("recovery must use the exact original target config, review and manifest")
    predecessor = records.get(api.release_name(review["expected_predecessor_release"]), {})
    if (predecessor.get("immutable") is not True
            or digest(predecessor.get("data", {})) != review["predecessor_record_sha256"]
            or canonical(predecessor["data"]) != started["predecessor_record"]):
        raise ValueError("recovery predecessor audit changed")
    deployments = assert_quiescent(api, documents)
    expected_images = {d["metadata"]["name"] + "/" + c["name"]: c["image"]
                       for d in documents if d["kind"] == "Deployment"
                       for c in d["spec"]["template"]["spec"]["containers"]}
    live_images = {d["metadata"]["name"] + "/" + c["name"]: c["image"]
                   for d in deployments for c in d["spec"]["template"]["spec"]["containers"]}
    if live_images != expected_images:
        raise ValueError("recovery requires the already rolled out target images")
    jobs = {j["metadata"]["name"]: j for j in items(api, "jobs")}
    for target in (d for d in documents if d["kind"] == "Job"):
        job = jobs.get(target["metadata"]["name"], {})
        expected = target["spec"]["template"]["spec"]["containers"]
        actual = job.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        if (job.get("status", {}).get("succeeded") != 1 or job.get("status", {}).get("failed", 0)
                or [(c["name"], c["image"]) for c in actual] != [(c["name"], c["image"]) for c in expected]):
            raise ValueError("recovery requires successful original target migration jobs")
    routes = maintenance_routes(api)
    if items(api, "targetgroupbindings"):
        raise ValueError("recovery requires maintenance routing without ALB bindings")
    for host in ("access." + config["domain"], "api." + config["domain"], config["app_domain"]):
        if api.http_status("https://" + host + "/", "--retry", "0") != "503":
            raise ValueError("recovery public route is not under maintenance")
    current = api.fingerprints(config, require_quiescent=True)
    if current != review["after_fingerprints"]:
        raise ValueError("recovery requires all three rehearsed after schemas; no SQL repair is allowed")
    assert_quiescent(api, documents)
    create_record(api, prefix + "-recovery-started", {"plan": canonical(plan), "fingerprints": canonical(current)})
    try:
        api.complete_rollout(config, sha, documents, current=current, review=review, settings=settings)
    except BaseException:
        cleanup_failed = False
        try:
            api.apply(routes)
        except Exception:
            cleanup_failed = True
        for d in deployments:
            try:
                api.kubectl("patch", "deployment", d["metadata"]["name"], "--type=merge",
                            "-p", '{"spec":{"replicas":0}}')
            except Exception:
                cleanup_failed = True
        create_record(api, prefix + "-recovery-failed", {
            "state": "operator-recovery-required", "containment": "unverified" if cleanup_failed else "requested"})
        raise


def guarded_deploy(api, config, sha, documents, **kwargs):
    api.validate_deploy_inputs(config, sha, documents, **kwargs)
    review = kwargs.get("review")
    maintenance = bool(review and review.get("migration_mode") == "maintenance-cutover")
    if maintenance and any(kwargs.get(k) for k in ("rollback", "bootstrap", "probe_recovery", "mail_health_recovery", "oauth_recovery")):
        raise ValueError("maintenance-cutover is deploy-only without bootstrap recovery")
    api.verify_target(config)
    records = items(api, "configmaps")
    by_name = {r["metadata"]["name"]: r for r in records}
    for name in by_name:
        if name.startswith(PREFIX) and name.endswith("-started"):
            release = name[len(PREFIX):-len("-started")]
            if release.endswith("-recovery"):
                release = release[:-len("-recovery")]
            if api.release_name(release) not in by_name:
                raise ValueError("unfinished maintenance attempt: keep downtime; explicit reviewed recovery required")
    if not maintenance:
        return api._deploy(config, sha, documents, **kwargs)
    if api.release_name(sha) in by_name:
        raise ValueError("completed maintenance release must use ordinary same-schema redeploy")
    predecessor = by_name.get(api.release_name(review["expected_predecessor_release"]))
    if (not predecessor or predecessor.get("immutable") is not True
            or predecessor.get("data", {}).get("safety_contract_version") != "2"
            or digest(predecessor["data"]) != review["predecessor_record_sha256"]):
        raise ValueError("preserved successful predecessor record does not match review")
    deployments = assert_quiescent(api, documents)
    live_images = {d["metadata"]["name"] + "/" + c["name"]: c["image"]
                   for d in deployments for c in d["spec"]["template"]["spec"]["containers"]}
    if live_images != review["expected_live_images"]:
        raise ValueError("live images differ from reviewed predecessor/hotfix inventory")
    routes = maintenance_routes(api)
    if items(api, "targetgroupbindings"):
        raise ValueError("wait for maintenance ingress to remove old ALB target bindings before Pod admission")
    for host in ("access." + config["domain"], "api." + config["domain"], config["app_domain"]):
        # 503 is the expected maintenance response, not a transient HTTP failure.
        # Retrying it can make curl fail while truncating its /dev/null output.
        if api.http_status("https://" + host + "/", "--retry", "0") != "503":
            raise ValueError("maintenance public route is not returning 503")
    api.smoke_settings()
    if api.fingerprints(config, require_quiescent=True) != review["before_fingerprints"]:
        raise ValueError("live before fingerprints differ from review")
    assert_quiescent(api, documents)
    data = {"review": canonical(review), "config": canonical(config),
            "manifest": yaml.safe_dump_all(documents, sort_keys=False),
            "predecessor_record": canonical(predecessor["data"])}
    create_record(api, PREFIX + sha + "-started", data)
    try:
        api._deploy(config, sha, documents, **kwargs)
    except BaseException:
        # A failed deployment is not a rollback. Keep the old audit and stop new writers.
        cleanup_failed = False
        try:
            api.apply(routes)
        except Exception:
            cleanup_failed = True
        for d in deployments:
            try:
                api.kubectl("patch", "deployment", d["metadata"]["name"], "--type=merge",
                            "-p", '{"spec":{"replicas":0}}')
            except Exception:
                cleanup_failed = True
        try:
            create_record(api, PREFIX + sha + "-failed", {
                "state": "operator-recovery-required", "containment": "unverified" if cleanup_failed else "requested"})
        except Exception:
            cleanup_failed = True
        print("Maintenance failed: do not retry/rollback or delete audit; verify ingress and writer shutdown."
              + (" Containment could not be completed." if cleanup_failed else ""), file=sys.stderr)
        raise
