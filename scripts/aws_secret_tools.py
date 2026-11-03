"""Secret updates without plaintext command arguments, with an AWSCURRENT compare-and-swap.

Callers must verify consumers before retiring a credential. Provider errors are deliberately
not echoed: they may contain connection strings or secret material.
"""
import json
import subprocess
import tempfile
import uuid
import warnings


def aws(region, *args, payload=None):
    command = ["aws", "--region", region, *args]
    # The macOS AWS CLI cannot reliably reread a pipe via /dev/stdin. Use a 0600
    # file inside a 0700 temporary directory, and remove it immediately afterward.
    with tempfile.TemporaryDirectory(prefix="fruition-secret-") as directory:
        if payload is not None:
            import os
            path = directory + "/input.json"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as handle:
                json.dump(payload, handle)
            command += ["--cli-input-json", "file://" + path]
        result = subprocess.run(command, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("AWS operation failed: " + " ".join(args[:2]))
    return json.loads(result.stdout) if result.stdout.strip() else {}


def read_secret(region, secret_id):
    record = aws(region, "secretsmanager", "get-secret-value", "--secret-id", secret_id)
    data = json.loads(record["SecretString"])
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object secret")
    return record["VersionId"], data


def promote_secret(region, secret_id, expected_version, data):
    """Do not overwrite a concurrent operator's AWSCURRENT version."""
    token = str(uuid.uuid4())
    stage = "fruition-staged-" + token
    aws(region, "secretsmanager", "put-secret-value", payload={
        "SecretId": secret_id, "ClientRequestToken": token,
        "SecretString": json.dumps(data), "VersionStages": [stage]})
    try:
        aws(region, "secretsmanager", "update-secret-version-stage", payload={
            "SecretId": secret_id, "VersionStage": "AWSCURRENT",
            "MoveToVersionId": token, "RemoveFromVersionId": expected_version})
    except RuntimeError:
        # A response can be lost after AWS committed the update. Read back the
        # version before reporting failure; never blindly retry with a new key.
        current, _ = read_secret(region, secret_id)
        if current != token:
            _remove_stage(region, secret_id, stage, token)
            raise RuntimeError("Secret promotion did not retain AWSCURRENT; reconcile before retrying") from None
    _remove_stage(region, secret_id, stage, token)
    return token


def _remove_stage(region, secret_id, stage, token):
    try:
        aws(region, "secretsmanager", "update-secret-version-stage", payload={
            "SecretId": secret_id, "VersionStage": stage, "RemoveFromVersionId": token})
    except RuntimeError:
        # Cleanup does not undo a successful promotion. A misleading failure
        # here could cause an operator to repeat an already completed rotation.
        warnings.warn("Temporary secret version label cleanup failed; inspect version metadata", RuntimeWarning)
