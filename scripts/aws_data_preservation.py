"""Fail-closed preservation checks for an explicitly lossless offline migration.

Only digests leave the database Job. Existing columns of every pre-migration table
are compared; newly added columns/tables may differ. Flyway may append history,
but the exact pre-migration history prefix must remain unchanged.
"""
import json
import re
from datetime import datetime

SERVICES = {"access", "document", "ai"}
IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]{0,62}")
HEX = re.compile(r"[0-9a-f]{64}")

METADATA_SQL = """SELECT COALESCE(jsonb_agg(jsonb_build_object('name', name, 'columns', columns) ORDER BY name), '[]')
FROM (SELECT t.tablename AS name, jsonb_agg(c.column_name ORDER BY c.ordinal_position) AS columns
FROM pg_tables t JOIN information_schema.columns c ON c.table_schema=t.schemaname AND c.table_name=t.tablename
WHERE t.schemaname='public' GROUP BY t.tablename) inventory;"""


def validate_preservation(evidence):
    if not isinstance(evidence, dict) or set(evidence) != {"databases", "snapshots", "restored_sha256", "credit_exemption_cutoff"}:
        raise ValueError("lossless migration requires data inventories, snapshots and restore digests")
    cutoff = evidence["credit_exemption_cutoff"]
    if not isinstance(cutoff, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", cutoff):
        raise ValueError("credit exemption requires a frozen UTC cutoff")
    datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    databases = evidence["databases"]
    if not isinstance(databases, dict) or set(databases) != SERVICES:
        raise ValueError("all three database inventories are required")
    if not isinstance(evidence["restored_sha256"], dict) or set(evidence["restored_sha256"]) != SERVICES:
        raise ValueError("all three restored database digests are required")
    for service, database in databases.items():
        if not isinstance(database, dict) or set(database) != {"tables", "sha256"}:
            raise ValueError("invalid database preservation fields")
        if not isinstance(database["sha256"], str) or not HEX.fullmatch(database["sha256"]):
            raise ValueError("invalid preserved data digest")
        if evidence["restored_sha256"][service] != database["sha256"]:
            raise ValueError("restored data must exactly match the preserved data")
        tables = database["tables"]
        if not isinstance(tables, list) or not tables:
            raise ValueError("empty table inventory is not preservation evidence")
        names = []
        for table in tables:
            if not isinstance(table, dict):
                raise ValueError("invalid table inventory")
            name = table.get("name")
            keys = {"name", "columns", "max_installed_rank"} if name == "flyway_schema_history" else {"name", "columns"}
            if set(table) != keys or not isinstance(name, str) or not IDENTIFIER.fullmatch(name):
                raise ValueError("invalid table identifier or fields")
            columns = table["columns"]
            if (not isinstance(columns, list) or not columns
                    or any(not isinstance(c, str) or not IDENTIFIER.fullmatch(c) for c in columns)
                    or len(set(columns)) != len(columns)):
                raise ValueError("invalid preserved columns")
            if name == "flyway_schema_history" and (type(table["max_installed_rank"]) is not int
                    or table["max_installed_rank"] < 0 or "installed_rank" not in columns):
                raise ValueError("invalid Flyway history boundary")
            names.append(name)
        if names != sorted(set(names)):
            raise ValueError("table inventory must be unique and sorted")
    snapshots = evidence["snapshots"]
    if not isinstance(snapshots, dict) or set(snapshots) != {"access", "core"}:
        raise ValueError("both RDS snapshots are required")
    for snapshot in snapshots.values():
        if not isinstance(snapshot, dict) or set(snapshot) != {"id", "created_after"}:
            raise ValueError("invalid snapshot evidence")
        if not isinstance(snapshot["id"], str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,254}", snapshot["id"]):
            raise ValueError("invalid snapshot identifier")
        try:
            instant = datetime.fromisoformat(snapshot["created_after"].replace("Z", "+00:00"))
            if instant.utcoffset() is None:
                raise ValueError()
        except (TypeError, AttributeError, ValueError):
            raise ValueError("snapshot boundary requires an explicit timezone") from None


def data_script(database, *, require_inventory):
    lines = ["set -eu", "umask 077", "export PGTZ=UTC",
             "trap 'rm -f /tmp/data-rows /tmp/data-digests' EXIT", ": > /tmp/data-digests"]
    if require_inventory:
        expected = [{k: t[k] for k in ("name", "columns")} for t in database["tables"]]
        # Identifiers have already been restricted to ASCII names: no SQL literals from data.
        literal = json.dumps(expected, separators=(",", ":"))
        query = METADATA_SQL.rstrip("; \n")
        lines += ["inventory=$(psql --dbname=\"$PGDATABASE\" -XAt -v ON_ERROR_STOP=1 2>/dev/null <<'SQL'",
                  "SELECT (inventory = '" + literal + "'::jsonb) FROM (" + query + ") AS q(inventory);", "SQL", ")",
                  '[ "$inventory" = t ] || { echo "preserved inventory differs" >&2; exit 1; }']
    for table in database["tables"]:
        name = table["name"]
        columns = ", ".join('"' + c + '"' for c in table["columns"])
        where = ""
        if name == "flyway_schema_history":
            where = " WHERE installed_rank <= " + str(table["max_installed_rank"])
            if require_inventory:
                lines += ['history=$(psql --dbname="$PGDATABASE" -XAt -v ON_ERROR_STOP=1 2>/dev/null <<\'SQL\'',
                          'SELECT COALESCE(max(installed_rank), 0) FROM public.flyway_schema_history;', 'SQL', ')',
                          f'[ "$history" = {table["max_installed_rank"]} ] || {{ echo "Flyway boundary differs" >&2; exit 1; }}']
        lines += ["psql --dbname=\"$PGDATABASE\" -Xq -v ON_ERROR_STOP=1 2>/dev/null > /tmp/data-rows <<'SQL'",
                  f'COPY (SELECT jsonb_build_array({columns})::text COLLATE "C" FROM public."{name}"{where} ORDER BY 1) TO STDOUT;',
                  "SQL", "row_digest=$(sha256sum /tmp/data-rows | cut -d ' ' -f 1)",
                  f"printf '%s:%s\\n' '{name}' \"$row_digest\" >> /tmp/data-digests",
                  "rm -f /tmp/data-rows"]
    lines += ["sha256sum /tmp/data-digests | cut -d ' ' -f 1", "rm -f /tmp/data-digests"]
    return "\n".join(lines) + "\n"


def data_digest(api, config, service, database, *, require_inventory):
    document = api.preflight_job(service, config, require_quiescent=True)
    container = document["spec"]["template"]["spec"]["containers"][0]
    script = container["command"][2]
    marker = "# 같은 PostgreSQL client"
    if marker not in script:
        raise ValueError("preflight ownership/quiescence boundary changed")
    # Keep verified TLS, per-role ownership and no-other-client checks. Replace only
    # schema dump output; credentials and original rows never appear in Job logs.
    container["command"][2] = script.split(marker, 1)[0] + data_script(database, require_inventory=require_inventory)
    document["metadata"]["name"] = service + "-data-preservation"
    api.job(document)
    value = api.kubectl("logs", "job/" + document["metadata"]["name"]).strip()
    if not HEX.fullmatch(value):
        raise ValueError(service + ": invalid preservation result")
    return value


def verify_snapshots(api, config, snapshots):
    instances = json.loads(api.run(["aws", "rds", "describe-db-instances", "--region", "ap-northeast-2", "--output", "json"]))["DBInstances"]
    for service, entry in snapshots.items():
        host = config["access_rds_endpoint" if service == "access" else "core_rds_endpoint"]
        matches = [i for i in instances if i["Endpoint"]["Address"] == host]
        if len(matches) != 1:
            raise ValueError("snapshot target database could not be identified")
        result = json.loads(api.run(["aws", "rds", "describe-db-snapshots", "--region", "ap-northeast-2",
                                    "--db-snapshot-identifier", entry["id"], "--output", "json"]))["DBSnapshots"]
        if len(result) != 1:
            raise ValueError("snapshot missing or ambiguous")
        snap = result[0]
        if (snap.get("Status") != "available" or snap.get("SnapshotType") != "manual"
                or snap.get("Encrypted") is not True or snap.get("DBInstanceIdentifier") != matches[0]["DBInstanceIdentifier"]
                or snap.get("DbiResourceId") != matches[0].get("DbiResourceId")
                or datetime.fromisoformat(snap["SnapshotCreateTime"].replace("Z", "+00:00"))
                    < datetime.fromisoformat(entry["created_after"].replace("Z", "+00:00"))):
            raise ValueError("snapshot is not a completed encrypted backup of the reviewed database")


def verify_data(api, config, evidence, *, before):
    validate_preservation(evidence)
    for service in sorted(SERVICES):
        database = evidence["databases"][service]
        if data_digest(api, config, service, database, require_inventory=before) != database["sha256"]:
            raise ValueError(service + ": original data changed; keep maintenance and do not resume")


def verify_before(api, config, evidence):
    validate_preservation(evidence)
    verify_snapshots(api, config, evidence["snapshots"])
    verify_data(api, config, evidence, before=True)


def verify_after(api, config, evidence):
    verify_data(api, config, evidence, before=False)


def prepare_credit_exemptions(api, config, evidence, *, job_name="existing-credit-exemptions"):
    """One offline Job; both credentials and the member CSV stay inside the Pod.

    Access is read only. Core changes only the exemption flag/updated_at or adds
    a zero-balance account. Existing balances, reservations and ledger stay intact.
    """
    validate_preservation(evidence)
    cutoff = evidence["credit_exemption_cutoff"]
    access = api.preflight_job("access", config, require_quiescent=True)
    document = api.preflight_job("document", config, require_quiescent=True)
    ac = access["spec"]["template"]["spec"]["containers"][0]
    dc = document["spec"]["template"]["spec"]["containers"][0]
    access_script = ac["command"][2].split("# 같은 PostgreSQL client", 1)[0]
    for name in ("RUNTIME_CREDENTIAL", "MIGRATION_CREDENTIAL"):
        access_script = access_script.replace(name, "ACCESS_" + name)
        for env in ac["env"]:
            if env["name"] == name:
                env["name"] = "ACCESS_" + name
                dc["env"].append(env)
    # The Access preflight checks this Secret before opening any DB connection.
    for env in ac["env"]:
        if env["name"] == "POSTHOG_PROJECT_TOKEN":
            dc["env"].append(env)
    export = f"""
cutoff_valid=$(psql --dbname="$PGDATABASE" -XAt -v ON_ERROR_STOP=1 2>/dev/null <<'SQL'
SELECT count(*) > 0 AND count(*) FILTER (WHERE created_at >= '{cutoff}'::timestamptz) = 0 FROM users;
SQL
)
[ "$cutoff_valid" = t ] || {{ echo 'credit cutoff does not include every existing member' >&2; exit 1; }}
psql --dbname="$PGDATABASE" -Xq -v ON_ERROR_STOP=1 2>/dev/null > /tmp/existing-credit-users.csv <<'SQL'
COPY (SELECT id FROM users WHERE created_at < '{cutoff}'::timestamptz ORDER BY id) TO STDOUT WITH (FORMAT csv);
SQL
"""
    import_sql = r"""
psql --dbname="$PGDATABASE" -Xq -v ON_ERROR_STOP=1 2>/dev/null <<'SQL'
BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';
CREATE TEMP TABLE existing_credit_users (user_id TEXT PRIMARY KEY CHECK (btrim(user_id) <> '')) ON COMMIT DROP;
\copy existing_credit_users FROM '/tmp/existing-credit-users.csv' WITH (FORMAT csv)
CREATE TEMP TABLE original_credit_balances ON COMMIT DROP AS SELECT user_id,balance,reserved FROM credit_accounts;
CREATE TEMP TABLE original_credit_entries ON COMMIT DROP AS SELECT count(*) AS n FROM credit_entries;
INSERT INTO credit_accounts(user_id,limit_exempt) SELECT user_id,true FROM existing_credit_users
ON CONFLICT(user_id) DO UPDATE SET limit_exempt=true,updated_at=now();
DO $credit$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM existing_credit_users) OR EXISTS (
  SELECT 1 FROM existing_credit_users u LEFT JOIN credit_accounts a USING(user_id)
  WHERE a.user_id IS NULL OR a.limit_exempt IS DISTINCT FROM true
 ) OR EXISTS (
  SELECT 1 FROM original_credit_balances b LEFT JOIN credit_accounts a USING(user_id)
  WHERE a.user_id IS NULL OR a.balance IS DISTINCT FROM b.balance OR a.reserved IS DISTINCT FROM b.reserved
 ) OR (SELECT n FROM original_credit_entries) <> (SELECT count(*) FROM credit_entries)
 THEN RAISE EXCEPTION 'credit preservation verification failed'; END IF;
END $credit$;
COMMIT;
SQL
rm -f /tmp/existing-credit-users.csv
echo 'credit exemptions verified'
"""
    document_script = dc["command"][2].split("# 같은 PostgreSQL client", 1)[0]
    dc["command"][2] = ("set -eu\numask 077\ntrap 'rm -f /tmp/existing-credit-users.csv' EXIT\n"
                         + access_script + export + document_script + import_sql)
    document["metadata"]["name"] = job_name
    api.job(document)
    result = api.kubectl("logs", "job/" + job_name).strip()
    if result != "credit exemptions verified":
        raise ValueError("credit exemptions were not verified; keep maintenance")
