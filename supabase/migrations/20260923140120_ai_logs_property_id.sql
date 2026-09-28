alter table public.ai_analysis_logs
  alter column property_id type bigint using null;

alter table public.ai_analysis_logs enable row level security;
drop policy if exists owner_select on public.ai_analysis_logs;
create policy owner_select on public.ai_analysis_logs for select to authenticated
  using (private.owns_property(property_id));
