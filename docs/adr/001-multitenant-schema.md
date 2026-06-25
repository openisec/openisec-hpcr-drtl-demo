# ADR 001: Multi-tenant Schema Strategy

**Date:** 2026-06-08  
**Status:** Deferred (Phase 2)  
**Deciders:** Nobuyuki Shibata  

---

## Context

HPCRDTL platform is designed as a multi-tenant SaaS where each organization
has its own data isolation. PostgreSQL schema-per-org is the chosen strategy.

## Decision

**Phase 1 (current):** All org-scoped tables reside in the `public` schema.
`ORG_SCHEMA = "public"` is used as a temporary placeholder.

**Phase 2 (deferred):** Each organization gets its own PostgreSQL schema:
`org_{uuid_without_hyphens}` (e.g. `org_14292024_45e3_4182_b584_7cf200d1e483`).

## Rationale for Deferral

- Phase 1 focus is on HPCRDTL core flow + Gemini integration + frontend
- Multi-tenant schema adds operational complexity before core value is proven
- All code is already structured to support the switch (ORG_SCHEMA variable,
  set_schema() in deps.py, -x schema= in Alembic)

## Phase 2 Implementation Plan

### 1. Organization Registration
When a new org is created, immediately provision its schema:

```python
# In auth.py register endpoint, after org creation:
db.execute(text(f"CREATE SCHEMA IF NOT EXISTS org_{org_schema_id}"))
# Run migration 0002 against new schema:
alembic_cfg = Config("alembic.ini")
command.upgrade(alembic_cfg, "head", x_arg=f"schema=org_{org_schema_id}")
```

### 2. Dynamic Schema Switching (deps.py)
```python
def get_org_db(...):
    org_schema = f"org_{str(org.id).replace('-', '_')}"
    set_schema(db, org_schema)
    return db, current_user, org
```

### 3. Model Update (org_models.py)
`ORG_SCHEMA` becomes a runtime variable, not a module-level constant.
SQLAlchemy `__table_args__` schema will need to match the migration schema.

### 4. Migration Update
`alembic -x schema=org_{uuid} upgrade head` creates tables in the correct schema.

## Security Benefits of Phase 2
- Complete data isolation between tenants at DB level
- No risk of cross-tenant data leakage via SQL
- Easier compliance (GDPR right to erasure: `DROP SCHEMA org_{uuid} CASCADE`)

## Files to Modify in Phase 2
- `app/models/org_models.py` — dynamic ORG_SCHEMA
- `app/core/deps.py` — get_org_db() dynamic schema
- `app/api/v1/endpoints/auth.py` — schema provisioning on org creation
- `migrations/env.py` — already supports -x schema= argument ✅
- `infra/database/migrations/` — add schema provisioning script

## Related TODOs in Code
- `app/models/org_models.py`: `# TODO: [PHASE-2]`
- `app/core/deps.py`: `# TODO: [PHASE-2]`
