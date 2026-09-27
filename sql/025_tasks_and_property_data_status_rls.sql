-- `tasks` and `property_data_status` were created by a standalone prototype
-- (never checked into this repo's migrations) with RLS enabled but zero
-- policies and zero grants to `authenticated` - so a normal user_client can
-- neither read nor write them yet. Bring them in line with every other
-- property-scoped table (see 003_mvp_ownership_rls.sql / 006_authenticated_
-- table_grants.sql): owner-only access via private.owns_property(property_id).

grant select, insert, update, delete on public.tasks, public.property_data_status to authenticated;

do $$
declare t text;
begin
  foreach t in array array['tasks', 'property_data_status'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists owner_all on public.%I', t);
    execute format(
      'create policy owner_all on public.%I for all to authenticated
         using (private.owns_property(property_id))
         with check (private.owns_property(property_id))', t);
  end loop;
end $$;
