"""명시적 실행만 하는 격리 PostgreSQL 통합 테스트. 기존 DB/포트/볼륨을 사용하지 않는다."""

import importlib.util
import subprocess
import time
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("aws_deploy", ROOT / "scripts/aws_deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class PreflightDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.container = "fruition-preflight-test-" + uuid.uuid4().hex[:12]
        cls.addClassCleanup(lambda: subprocess.run(["docker", "rm", "-fv", cls.container], capture_output=True))
        cls.command(["docker", "run", "-d", "--name", cls.container, "-e", "POSTGRES_PASSWORD=isolated_test_admin",
                 "-e", "POSTGRES_INITDB_ARGS=--auth-host=scram-sha-256",
                 "-v", f"{ROOT / 'infra/postgres'}:/work:ro", "postgres:16-alpine"])
        for _ in range(60):
            result = subprocess.run(["docker", "exec", cls.container, "pg_isready", "-h", "127.0.0.1", "-U", "postgres"], capture_output=True)
            if result.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("격리 PostgreSQL 준비 실패")
        cls.sql("CREATE ROLE bootstrap LOGIN CREATEDB CREATEROLE PASSWORD 'isolated_test_admin'")
        args = ["docker", "exec", "-e", "DB_ISOLATION_TARGET=all", "-e", "PGHOST=127.0.0.1",
                "-e", "POSTGRES_ADMIN_USER=bootstrap", "-e", "POSTGRES_ADMIN_PASSWORD=isolated_test_admin"]
        for prefix in ("ACCESS", "CORE", "AI"):
            args += ["-e", f"{prefix}_DB_RUNTIME_PASSWORD=runtime_test_password",
                     "-e", f"{prefix}_DB_MIGRATION_PASSWORD=migration_test_password",
                     "-e", f"{prefix}_DB_NAME={prefix.lower()}_db",
                     "-e", f"{prefix}_DB_RUNTIME_USER={prefix.lower()}_runtime",
                     "-e", f"{prefix}_DB_MIGRATION_USER={prefix.lower()}_migration"]
        cls.command(args + [cls.container, "bash", "/work/init-db-isolation.sh"])

    @staticmethod
    def command(args, input=None):
        return subprocess.run(args, input=input, text=True, capture_output=True, check=True).stdout.strip()

    @classmethod
    def sql(cls, sql, database="postgres"):
        return cls.command(["docker", "exec", cls.container, "psql", "-U", "postgres", "-d", database, "-v", "ON_ERROR_STOP=1", "-Atc", sql])

    def preflight(self, service="access", runtime="runtime_test_password", migration="migration_test_password", *, uri_replace=None, expected_host="127.0.0.1"):
        # 운영 SQL과 shell을 그대로 실행하되 TLS 없는 임시 DB 연결만 치환한다.
        document = deploy.preflight_job(service, {"access_rds_endpoint": "127.0.0.1", "core_rds_endpoint": expected_host})
        script = document["spec"]["template"]["spec"]["containers"][0]["command"][2]
        if service == "ai":
            runtime = f"postgresql://ai_runtime:{runtime}@127.0.0.1:5432/ai_db"
            migration = f"postgresql://ai_migration:{migration}@127.0.0.1:5432/ai_db"
            if uri_replace:
                runtime = runtime.replace(*uri_replace)
                migration = migration.replace(*uri_replace)
        return self.command(["docker", "exec", "-i", "-e", "PGSSLMODE=disable", "-e", "PGCONNECT_TIMEOUT=3",
                         "-e", f"RUNTIME_CREDENTIAL={runtime}", "-e", f"MIGRATION_CREDENTIAL={migration}",
                         self.container, "sh", "-s"], input=script)

    def test_actual_bootstrap_roles_passwords_owners_and_fingerprints(self):
        for service in ("access", "document", "ai"):
            with self.subTest(service=service):
                first = self.preflight(service)
                self.assertRegex(first, r"^[0-9a-f]{64}$")
                self.assertEqual(first, self.preflight(service))
                for role in ("runtime", "migration"):
                    with self.subTest(role=role), self.assertRaises(subprocess.CalledProcessError):
                        self.preflight(service, **{role: "wrong_password"})
        for replacement in (("127.0.0.1", "wrong-target.invalid"), (":5432/", ":5433/"),
                            ("ai_runtime:", "core_runtime:"), ("/ai_db", "/core_db"),
                            ("/ai_db", "/ai_db?sslmode=disable"),
                            ("/ai_db", "/ai_db?host=wrong-target.invalid")):
            with self.subTest(uri=replacement), self.assertRaises(subprocess.CalledProcessError) as failure:
                self.preflight("ai", uri_replace=replacement)
            self.assertIn("AI database URI contract failed", failure.exception.stdout)
        with self.assertRaises(subprocess.CalledProcessError) as failure:
            self.preflight("ai", expected_host="wrong-target.invalid")
        self.assertIn("AI database URI contract failed", failure.exception.stdout)
        self.sql("ALTER DATABASE access_db OWNER TO postgres")
        with self.assertRaises(subprocess.CalledProcessError):
            self.preflight()
        self.sql("ALTER DATABASE access_db OWNER TO access_migration")
        self.sql("ALTER SCHEMA public OWNER TO postgres", "access_db")
        with self.assertRaises(subprocess.CalledProcessError):
            self.preflight()
        self.sql("ALTER SCHEMA public OWNER TO access_migration", "access_db")
        before = self.preflight()
        self.sql("SET ROLE access_migration; CREATE TABLE public.preflight_example(id integer)", "access_db")
        self.assertNotEqual(before, self.preflight())
        self.sql("REVOKE INSERT ON public.preflight_example FROM access_runtime", "access_db")
        with self.assertRaises(subprocess.CalledProcessError):
            self.preflight()
        self.sql("GRANT INSERT ON public.preflight_example TO access_runtime", "access_db")
        self.sql("GRANT CREATE ON SCHEMA public TO access_runtime", "access_db")
        with self.assertRaises(subprocess.CalledProcessError):
            self.preflight()
        self.sql("REVOKE CREATE ON SCHEMA public FROM access_runtime", "access_db")
        self.sql("GRANT CONNECT ON DATABASE core_db TO access_runtime")
        with self.assertRaises(subprocess.CalledProcessError):
            self.preflight()
        self.sql("REVOKE CONNECT ON DATABASE core_db FROM access_runtime")
        self.sql("DROP DATABASE access_db")
        with self.assertRaises(subprocess.CalledProcessError):
            self.preflight()
        self.sql("DROP OWNED BY core_runtime", "core_db")
        self.sql("DROP ROLE core_runtime")
        with self.assertRaises(subprocess.CalledProcessError):
            self.preflight("document")


if __name__ == "__main__":
    unittest.main()
