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
