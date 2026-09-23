-- Align ai_analysis_logs.property_id with properties.id (bigint).
-- The only existing row has a NULL property_id, so no data is lost.
alter table public.ai_analysis_logs
  alter column property_id type bigint using null;

alter table public.ai_analysis_logs enable row level security;
drop policy if exists owner_select on public.ai_analysis_logs;
create policy owner_select on public.ai_analysis_logs for select to authenticated
  using (private.owns_property(property_id));
