"""
Apply Alembic migrations to public and to every tenant schema registered in
public.organizations.pg_schema (full UUID-suffixed names only).

Short-form schemas such as org_6bfec2df are empty orphans and are NOT touched,
because this script only reads names from organizations.pg_schema.

Intended to run inside the Cloud Run Job (same image as the API, WORKDIR /app,
DATABASE_URL injected from Secret Manager, VPC connector attached), because the
stg/prd/demo databases are private-IP only:

    python migrations/apply_all_tenants.py --dry-run   # show current revisions only
    python migrations/apply_all_tenants.py             # upgrade head for every schema
"""
import os
import subprocess
import sys

import psycopg2

DRY_RUN = "--dry-run" in sys.argv

dsn = os.environ["DATABASE_URL"]
if dsn.startswith("postgresql+psycopg2://"):
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://", 1)


def alembic(args, schema=None):
    cmd = [sys.executable, "-m", "alembic"]
    if schema and schema != "public":
        cmd += ["-x", "schema=" + schema]
    cmd += args
    result = subprocess.run(cmd, capture_output=True, text=True)
    lines = [ln for ln in (result.stdout + result.stderr).splitlines() if ln.strip()]
    return result.returncode, lines


def current_rev(schema):
    code, lines = alembic(["current"], schema)
    revs = [ln for ln in lines if not ln.startswith("INFO")]
    return code, (revs[-1] if revs else "(none)")


conn = psycopg2.connect(dsn)
conn.autocommit = True
cur = conn.cursor()
cur.execute("SELECT name, pg_schema FROM public.organizations ORDER BY created_at;")
orgs = cur.fetchall()
cur.close()
conn.close()

targets = [("(public)", "public")] + [(n, s) for n, s in orgs]
print("targets: %d (public + %d tenant schemas), dry_run=%s\n" % (len(targets), len(orgs), DRY_RUN))

failures = []
for name, schema in targets:
    code, before = current_rev(schema)
    print("=== %s [%s] ===" % (name, schema))
    print("  before: %s" % before)
    if DRY_RUN:
        continue
    code, lines = alembic(["upgrade", "head"], schema)
    for ln in lines:
        if "Running upgrade" in ln or "Error" in ln or "error" in ln:
            print("  " + ln)
    if code != 0:
        failures.append((name, schema))
        print("  FAILED (exit code %d)" % code)
        continue
    _, after = current_rev(schema)
    print("  after:  %s" % after)

if failures:
    print("\n[!] %d schema(s) failed:" % len(failures))
    for name, schema in failures:
        print("  - %s (%s)" % (name, schema))
    sys.exit(1)
print("\nDone." if not DRY_RUN else "\nDry run finished (nothing was changed).")
