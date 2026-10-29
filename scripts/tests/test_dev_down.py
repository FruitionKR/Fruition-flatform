"""격리된 Docker 대역으로 종료 시간과 볼륨 보존 옵션을 확인한다."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DevDownTest(unittest.TestCase):
    def test_shutdown_modes(self):
        for options, timeout in (([], "30"), (["--graceful"], "7800"), (["--volumes"], "30")):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "scripts/lib").mkdir(parents=True)
                (root / "infra").mkdir()
                shutil.copy(ROOT / "scripts/dev-down.sh", root / "scripts/dev-down.sh")
                (root / "scripts/lib/runtime.sh").write_text("runtime_stop() { :; }\n")
                logs = root / "scripts/logs-up.sh"
                logs.write_text("#!/bin/sh\nexit 0\n")
                logs.chmod(0o755)
                docker = root / "docker"
                docker.write_text('#!/bin/sh\nif [ "$1" = compose ]; then printf "%s\\n" "$@" > "$CAPTURE"; fi\n')
                docker.chmod(0o755)
                capture = root / "args"
                env = dict(os.environ, PATH=f"{root}:{os.environ['PATH']}", CAPTURE=str(capture))
                subprocess.run(["bash", str(root / "scripts/dev-down.sh"), *options], env=env, check=True, capture_output=True)
                args = capture.read_text().splitlines()
                self.assertIn(str(root / "infra/compose.converter.yml"), args)
                self.assertEqual(args[args.index("--timeout") + 1], timeout)
                self.assertEqual("-v" in args, "--volumes" in options)
