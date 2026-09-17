"""Runner readiness must reject wrong identities, open endpoints and excess RBAC."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]


class RunnerTests(unittest.TestCase):
    def check_runner(self, scenario):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            aws = root / "aws"
            aws.write_text('''#!/usr/bin/env python3
import json, os, sys
case = os.environ['SCENARIO']
if sys.argv[1] == 'sts':
    account = '999999999999' if case == 'account' else '123456789012'
    role = 'admin' if case == 'role' else 'fruition-github-deploy'
    print(json.dumps({'Account': account, 'Arn': f'arn:aws:sts::{account}:assumed-role/{role}/test'}))
elif sys.argv[2] == 'describe-cluster':
    print(json.dumps({'cluster': {'status': 'ACTIVE', 'resourcesVpcConfig': {'endpointPrivateAccess': True, 'endpointPublicAccess': case == 'public'}}}))
''')
            kubectl = root / "kubectl"
            kubectl.write_text('''#!/usr/bin/env python3
import os, sys
case = os.environ['SCENARIO']
if 'auth' not in sys.argv:
    sys.exit(0)
if case == 'transport':
    print('Connection refused', file=sys.stderr)
    sys.exit(1)
denied = 'secrets' in sys.argv or 'rolebindings' in sys.argv or 'default' in sys.argv
if case == 'excess': denied = False
if case == 'missing': denied = True
print('no' if denied else 'yes')
sys.exit(1 if denied else 0)
''')
            aws.chmod(0o755)
            kubectl.chmod(0o755)
            return subprocess.run(
                ['bash', str(ROOT / 'scripts/aws-runner-check.sh')],
                env={**os.environ, 'PATH': f'{root}:{os.environ["PATH"]}',
                     'SCENARIO': scenario, 'KUBECONFIG': str(root / 'config'),
                     'DEPLOY_ROLE': 'arn:aws:iam::123456789012:role/fruition-github-deploy'},
                capture_output=True, text=True)

    def test_ready_runner(self):
        result = self.check_runner('ready')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('PASS:', result.stdout)

    def test_readiness_rejects_invalid_identity_network_or_permissions(self):
        for scenario in ('account', 'role', 'public', 'excess', 'missing', 'transport'):
            with self.subTest(scenario=scenario):
                self.assertNotEqual(0, self.check_runner(scenario).returncode)

    def test_self_hosted_workflows_are_manual_main_environment_jobs(self):
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            workflow = yaml.safe_load(path.read_text())
            for job in workflow.get('jobs', {}).values():
                if 'self-hosted' not in job.get('runs-on', []):
                    continue
                trigger = workflow.get('on', workflow.get(True))
                self.assertEqual({'workflow_dispatch'}, set(trigger), str(path))
                self.assertEqual("github.ref == 'refs/heads/main'", job['if'])
                self.assertEqual('feedback', job['environment'])
                self.assertEqual('true', job['env']['AWS_EC2_METADATA_DISABLED'])


if __name__ == '__main__':
    unittest.main()
