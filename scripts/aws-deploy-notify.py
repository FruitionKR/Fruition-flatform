"""Publish a sanitized deployment failure through the existing SNS/Lambda path."""
import datetime
import json
import os
import re
import subprocess

config = json.loads(os.environ["DEPLOY_CONFIG"])
account = config["account_id"]
if not re.fullmatch(r"\d{12}", account):
    raise SystemExit("Invalid target account")
run_url = os.environ["RUN_URL"]
if not re.fullmatch(r"https://github\.com/FruitionKR/Fruition-flatform/actions/runs/\d+", run_url):
    raise SystemExit("Invalid workflow URL")
message = {
    "AlarmName": "fruition-deployment-failed",
    "NewStateValue": "ALARM",
    "NewStateReason": "배포 실패. DB를 자동으로 되돌리지 않았습니다. 확인: " + run_url,
    "AWSAccountId": account,
    "StateChangeTime": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
# No webhook or application secret is read by this workflow.
subprocess.run(["aws", "sns", "publish", "--region", "ap-northeast-2", "--topic-arn",
                f"arn:aws:sns:ap-northeast-2:{account}:fruition-operations-alerts",
                "--message", json.dumps(message, ensure_ascii=False)], check=True, capture_output=True)
