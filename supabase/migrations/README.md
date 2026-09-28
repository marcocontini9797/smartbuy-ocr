# Supabase migrations

`supabase/migrations/` is the canonical migration history for the SmartBuy Supabase project.

Rules:
- Every file in this directory mirrors one migration recorded in `supabase_migrations.schema_migrations`.
- Filenames keep the exact live migration version and name: `<version>_<name>.sql`.
- Do not add a migration here with a timestamp that is not recorded/applied through the normal Supabase migration workflow.
- Do not edit an already-applied migration. Add a new migration for subsequent changes.
- The legacy `sql/` directory contains historical/bootstrap scripts and implementation references. It is not the canonical migration ledger.
- Before release, compare this directory with the live Supabase migration list and require zero missing and zero extra migration files.

Reconciliation performed on 2026-09-28: 28 live migrations matched 28 repository migration files, with zero missing and zero extra files.
