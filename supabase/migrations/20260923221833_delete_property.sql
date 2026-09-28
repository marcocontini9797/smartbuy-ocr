create or replace function public.smartbuy_delete_property(p_property_id bigint)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_paths jsonb;
  v_documents bigint[];
begin
  if not exists (select 1 from properties where id = p_property_id and user_id = auth.uid()) then
    raise exception 'property_not_found' using errcode = '23503';
  end if;

  select coalesce(array_agg(distinct d.id), '{}') into v_documents
  from documents d
  where d.fascicolo_id = p_property_id::text
     or d.id::text in (select document_id from document_analyses where property_id = p_property_id);

  select coalesce(jsonb_agg(storage_path) filter (where storage_path is not null), '[]'::jsonb) into v_paths
  from documents where id = any(v_documents);

  delete from property_facts where property_id = p_property_id;
  delete from fact_provenance where property_id = p_property_id or document_id = any(v_documents);
  delete from ai_feedback where property_id = p_property_id or document_id = any(v_documents);
  delete from ai_analysis_logs where property_id = p_property_id or document_id = any(v_documents);
  delete from document_intelligence_results where property_id = p_property_id or document_id = any(v_documents);
  delete from document_classifications where document_id = any(v_documents);
  delete from document_text_extractions where document_id = any(v_documents);
  delete from smartbuy_run_stages where run_id in (select run_id from smartbuy_analysis_runs where property_id = p_property_id);
  delete from smartbuy_operational_evidence where property_id = p_property_id;
  delete from smartbuy_analysis_runs where property_id = p_property_id;
  delete from smartbuy_document_requests where property_id = p_property_id;
  delete from document_analyses where property_id = p_property_id;
  delete from documents where id = any(v_documents);
  delete from properties where id = p_property_id;

  return jsonb_build_object('deleted', true, 'documents', coalesce(array_length(v_documents, 1), 0), 'storage_paths', v_paths);
end;
$$;

revoke execute on function public.smartbuy_delete_property(bigint) from public, anon;
grant execute on function public.smartbuy_delete_property(bigint) to authenticated;
