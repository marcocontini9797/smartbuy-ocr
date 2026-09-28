create index if not exists properties_user_id_idx on public.properties (user_id);
create index if not exists property_facts_property_id_idx on public.property_facts (property_id);
create index if not exists property_facts_source_document_idx on public.property_facts (source_document_id);
create index if not exists fact_provenance_property_id_idx on public.fact_provenance (property_id);
create index if not exists fact_provenance_document_id_idx on public.fact_provenance (document_id);
create index if not exists smartbuy_operational_evidence_run_id_idx on public.smartbuy_operational_evidence (run_id);
create index if not exists smartbuy_feedback_signals_event_idx on public.smartbuy_feedback_signals (feedback_event_id);
create index if not exists smartbuy_recalculation_jobs_property_idx on public.smartbuy_recalculation_jobs (property_id);

drop policy if exists "Users can view own properties" on public.properties;
drop policy if exists "Users can insert own properties" on public.properties;
drop policy if exists "Users can update own properties" on public.properties;
drop policy if exists "Users can delete own properties" on public.properties;
create policy "Users can view own properties" on public.properties for select to authenticated
  using ((select auth.uid()) = user_id);
create policy "Users can insert own properties" on public.properties for insert to authenticated
  with check ((select auth.uid()) = user_id);
create policy "Users can update own properties" on public.properties for update to authenticated
  using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
create policy "Users can delete own properties" on public.properties for delete to authenticated
  using ((select auth.uid()) = user_id);

drop policy if exists "Users can view their property analyses" on public.document_analyses;
drop policy if exists "Users can insert analyses for their properties" on public.document_analyses;
drop policy if exists "Users can update analyses for their properties" on public.document_analyses;
create policy "Users can view their property analyses" on public.document_analyses for select to authenticated
  using (property_id in (select p.id from public.properties p where p.user_id = (select auth.uid())));
create policy "Users can insert analyses for their properties" on public.document_analyses for insert to authenticated
  with check (property_id in (select p.id from public.properties p where p.user_id = (select auth.uid())));
create policy "Users can update analyses for their properties" on public.document_analyses for update to authenticated
  using (property_id in (select p.id from public.properties p where p.user_id = (select auth.uid())));

do $$
declare t text;
begin
  foreach t in array array['smartbuy_analysis_runs', 'smartbuy_document_requests', 'smartbuy_operational_evidence'] loop
    execute format('drop policy if exists %I on public.%I',
      case t when 'smartbuy_analysis_runs' then 'analysis_runs_owner'
             when 'smartbuy_document_requests' then 'document_requests_owner'
             else 'operational_evidence_owner' end, t);
    execute format(
      'create policy %I on public.%I for all to authenticated
         using (exists (select 1 from public.properties p where p.id = %I.property_id and p.user_id = (select auth.uid())))
         with check (exists (select 1 from public.properties p where p.id = %I.property_id and p.user_id = (select auth.uid())))',
      case t when 'smartbuy_analysis_runs' then 'analysis_runs_owner'
             when 'smartbuy_document_requests' then 'document_requests_owner'
             else 'operational_evidence_owner' end, t, t, t);
  end loop;
end $$;

drop policy if exists run_stages_owner on public.smartbuy_run_stages;
create policy run_stages_owner on public.smartbuy_run_stages for all to authenticated
  using (exists (select 1 from public.smartbuy_analysis_runs r join public.properties p on p.id = r.property_id
                 where r.run_id = smartbuy_run_stages.run_id and p.user_id = (select auth.uid())))
  with check (exists (select 1 from public.smartbuy_analysis_runs r join public.properties p on p.id = r.property_id
                      where r.run_id = smartbuy_run_stages.run_id and p.user_id = (select auth.uid())));

drop policy if exists feedback_event_owner_insert on public.smartbuy_feedback_events;
drop policy if exists feedback_event_owner_read on public.smartbuy_feedback_events;
create policy feedback_event_owner_insert on public.smartbuy_feedback_events for insert to authenticated
  with check (actor_user_id = (select auth.uid())::text
              and exists (select 1 from public.properties p where p.id = property_id and p.user_id = (select auth.uid())));
create policy feedback_event_owner_read on public.smartbuy_feedback_events for select to authenticated
  using (actor_user_id = (select auth.uid())::text);

drop policy if exists feedback_signal_owner_insert on public.smartbuy_feedback_signals;
drop policy if exists feedback_signal_owner_read on public.smartbuy_feedback_signals;
create policy feedback_signal_owner_insert on public.smartbuy_feedback_signals for insert to authenticated
  with check (actor_id = (select auth.uid())::text
              and exists (select 1 from public.properties p where p.id = property_id and p.user_id = (select auth.uid())));
create policy feedback_signal_owner_read on public.smartbuy_feedback_signals for select to authenticated
  using (actor_id = (select auth.uid())::text);

drop policy if exists feedback_job_owner_insert on public.smartbuy_recalculation_jobs;
drop policy if exists feedback_job_owner_read on public.smartbuy_recalculation_jobs;
create policy feedback_job_owner_insert on public.smartbuy_recalculation_jobs for insert to authenticated
  with check (exists (select 1 from public.properties p where p.id = property_id and p.user_id = (select auth.uid())));
create policy feedback_job_owner_read on public.smartbuy_recalculation_jobs for select to authenticated
  using (exists (select 1 from public.properties p where p.id = property_id and p.user_id = (select auth.uid())));

grant select on public.omi_quotes, public.omi_zones to authenticated;
drop policy if exists omi_quotes_read on public.omi_quotes;
drop policy if exists omi_zones_read on public.omi_zones;
create policy omi_quotes_read on public.omi_quotes for select to authenticated using (true);
create policy omi_zones_read on public.omi_zones for select to authenticated using (true);
alter function public.smartbuy_omi_zone_quotes(double precision, double precision) security invoker;
alter function public.smartbuy_comune_bbox(text) security invoker;

revoke execute on function public.st_estimatedextent(text, text) from anon, authenticated;
revoke execute on function public.st_estimatedextent(text, text, text) from anon, authenticated;
revoke execute on function public.st_estimatedextent(text, text, text, boolean) from anon, authenticated;
