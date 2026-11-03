"""URI policy boundaries. Live AWS CheckCapacity/probes verify WAF transforms."""
import json
import posixpath
import re
import unittest
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
POLICY = json.loads((ROOT / "infra/waf/sensitive-paths.json").read_text())


def matches(path):
    # One decoding pass, as configured. This is not a WAF transformation emulator.
    path = posixpath.normpath(unquote(path)).lower()
    return bool(re.search(POLICY["path_regex"], path))


class SensitivePathsTests(unittest.TestCase):
    def test_blocks_repository_and_environment_path_segments(self):
        for path in ["/.git", "/.git/config", "/.git-credentials", "/.gitconfig", "/.envrc", "/nested/.git/HEAD", "/.env",
                     "/.env.local", "/.env.swp", "/config/.env", "/.env~",
                     "/%2egit/config", "/%2Eenv.local", "/.GIT/config",
                     "/a/../.env", "//.git/config", "/.env;x", "/.git;/config", "/.env%3bx"]:
            with self.subTest(path=path):
                self.assertTrue(matches(path))

    def test_preserves_normal_routes_and_similarly_named_resources(self):
        for path in ["/", "/healthz", "/.well-known/security.txt",
                     "/_next/static/env.js", "/.gitignore", "/.environment",
                     "/api/workspaces", "/api/auth/refresh", "/api/invitations/accept",
                     "/api/workspaces/ws_123/documents/markdown", "/environment",
                     "/api/users/me/credits"]:
            with self.subTest(path=path):
                self.assertFalse(matches(path))

    def test_single_decode_does_not_claim_double_encoding_coverage(self):
        self.assertFalse(matches("/%252egit/config"))


if __name__ == "__main__":
    unittest.main()
