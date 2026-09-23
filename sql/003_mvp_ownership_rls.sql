-- SmartBuy MVP: account-owned access for every workspace table.
-- The backend reads and writes with the user's JWT, so each table the
-- workspace touches needs an owner policy. Service role bypasses RLS.

create schema if not exists private;
grant usage on schema private to authenticated;

create or replace function private.owns_property(pid bigint)
returns boolean
language sql
stable
security invoker
set search_path = ''
as $$
  select exists (
    select 1 from public.properties p
    where p.id = pid and p.user_id = auth.uid()
  );
$$;
grant execute on function private.owns_property(bigint) to authenticated;

-- 1. Align property_id types with properties.id (bigint).
--    All current values are NULL, so no data is lost.
alter table public.fact_provenance
  alter column property_id type bigint using null;
alter table public.document_intelligence_results
  alter column property_id type bigint using null;
alter table public.ai_feedback
  alter column property_id type bigint using null;

-- Backfill provenance ownership from the facts that reference it.
update public.fact_provenance fp
set property_id = f.property_id
from public.property_facts f
where f.provenance_id = fp.id and fp.property_id is null;

-- 2. Property-scoped tables: owner can do everything on their own rows.
do $$
declare t text;
begin
  foreach t in array array[
    'property_facts', 'property_evidence', 'property_issues',
    'property_knowledge_links', 'llm_audit_logs', 'fact_provenance',
    'document_intelligence_results', 'ai_feedback',
    'property_travel_times', 'property_location_scores'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists owner_all on public.%I', t);
    execute format(
      'create policy owner_all on public.%I for all to authenticated
         using (private.owns_property(property_id))
         with check (private.owns_property(property_id))', t);
  end loop;
end $$;

-- 3. Documents: the uploader owns the row; readers of an owned property
--    also see documents linked through document_analyses.
drop policy if exists documents_owner_select on public.documents;
drop policy if exists documents_owner_insert on public.documents;
drop policy if exists documents_owner_update on public.documents;
create policy documents_owner_select on public.documents for select to authenticated
  using (
    agente_id = (select auth.uid())::text
    or exists (
      select 1 from public.document_analyses a
      where a.document_id = documents.id::text
        and private.owns_property(a.property_id)
    )
  );
create policy documents_owner_insert on public.documents for insert to authenticated
  with check (agente_id = (select auth.uid())::text);
create policy documents_owner_update on public.documents for update to authenticated
  using (agente_id = (select auth.uid())::text)
  with check (agente_id = (select auth.uid())::text);

-- 4. Location profile tables (previously without RLS).
alter table public.user_location_profiles enable row level security;
drop policy if exists owner_all on public.user_location_profiles;
create policy owner_all on public.user_location_profiles for all to authenticated
  using (user_id = (select auth.uid()))
  with check (user_id = (select auth.uid()));

do $$
declare t text;
begin
  foreach t in array array[
    'user_destinations', 'user_location_preferences', 'user_location_constraints'
  ] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists owner_all on public.%I', t);
    execute format(
      'create policy owner_all on public.%I for all to authenticated
         using (exists (select 1 from public.user_location_profiles p
                        where p.id = profile_id and p.user_id = (select auth.uid())))
         with check (exists (select 1 from public.user_location_profiles p
                             where p.id = profile_id and p.user_id = (select auth.uid())))', t);
  end loop;
end $$;

-- 5. Properties are private to their owner: drop anonymous read-all.
drop policy if exists "Lettura pubblica immobili" on public.properties;

-- 6. Internal helper must not be callable from the public API.
revoke execute on function public.rls_auto_enable() from anon, authenticated, public;
