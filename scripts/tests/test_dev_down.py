"""격리된 Docker 대역으로 converter 선행 정지와 종료 옵션을 확인한다."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DevDownTest(unittest.TestCase):
    def run_shutdown(self, options, *, stop_fails=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "scripts/lib").mkdir(parents=True)
            (root / "infra").mkdir()
            shutil.copy(ROOT / "scripts/dev-down.sh", root / "scripts/dev-down.sh")
            (root / "scripts/lib/runtime.sh").write_text("runtime_stop() { :; }\n")
            logs = root / "scripts/logs-up.sh"
            logs.write_text("#!/bin/sh\nexit 0\n")
            logs.chmod(0o755)
            docker = root / "docker"
            docker.write_text(f"#!{sys.executable}\n" + """
import json, os, sys
with open(os.environ["CAPTURE"], "a") as output:
    output.write(json.dumps(sys.argv[1:]) + "\\n")
if "stop" in sys.argv and os.environ["STOP_FAILS"] == "true":
    sys.exit(17)
""")
            docker.chmod(0o755)
            capture = root / "args"
            env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", CAPTURE=str(capture),
                       STOP_FAILS=str(stop_fails).lower())
            result = subprocess.run(["bash", str(root / "scripts/dev-down.sh"), *options],
                                    env=env, capture_output=True, text=True)
            calls = [json.loads(line) for line in capture.read_text().splitlines()]
            return result, calls

    def test_shutdown_modes(self):
        for options, timeout in (([], "30"), (["--graceful"], "7800"),
                                 (["--volumes"], "30"), (["--graceful", "--volumes"], "7800")):
            with self.subTest(options=options):
                result, calls = self.run_shutdown(options)
                self.assertEqual(result.returncode, 0, result.stderr)
                compose_calls = [call for call in calls if call[0] == "compose"]
                self.assertEqual(len(compose_calls), 2)
                stop, down = compose_calls
                self.assertEqual(stop[-4:], ["stop", "--timeout", timeout, "markitdown"])
                self.assertIn("down", down)
                self.assertEqual(down[down.index("--timeout") + 1], timeout)
                self.assertEqual("-v" in down, "--volumes" in options)
                for call in compose_calls:
                    self.assertTrue(any(arg.endswith("/infra/compose.converter.yml") for arg in call))
                self.assertEqual(stop[:stop.index("stop")], down[:down.index("down")])

    def test_converter_stop_failure_preserves_dependencies_and_volumes(self):
        result, calls = self.run_shutdown(["--graceful", "--volumes"], stop_fails=True)
        self.assertEqual(result.returncode, 17)
        self.assertTrue(any("stop" in call for call in calls))
        self.assertFalse(any("down" in call for call in calls))
        self.assertFalse(any(call[:2] == ["volume", "rm"] for call in calls))
