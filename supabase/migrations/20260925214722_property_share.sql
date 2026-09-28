alter table public.properties add column if not exists share_token text unique;
alter table public.properties add column if not exists share_enabled boolean not null default false;
create index if not exists properties_share_token_idx on public.properties (share_token) where share_token is not null;

create or replace function public.smartbuy_shared_fascicolo(p_token text)
returns jsonb
language sql
stable
security definer
set search_path = public, extensions
as $$
  select case when p.id is null then null else jsonb_build_object(
    'property', to_jsonb(p) - 'user_id' - 'share_token',
    'documents', coalesce((
      select jsonb_agg(to_jsonb(d) - 'storage_path' - 'agente_id')
      from documents d
      where d.fascicolo_id = p.id::text
    ), '[]'::jsonb),
    'analyses', coalesce((
      select jsonb_agg(to_jsonb(a))
      from document_analyses a
      where a.property_id = p.id
    ), '[]'::jsonb),
    'facts', coalesce((
      select jsonb_agg(to_jsonb(f))
      from property_facts f
      where f.property_id = p.id
    ), '[]'::jsonb),
    'provenance', coalesce((
      select jsonb_agg(to_jsonb(pr))
      from fact_provenance pr
      where pr.id in (
        select f2.provenance_id from property_facts f2
        where f2.property_id = p.id and f2.provenance_id is not null
      )
    ), '[]'::jsonb)
  ) end
  from properties p
  where p.share_token = p_token and p.share_enabled = true
  limit 1;
$$;

revoke execute on function public.smartbuy_shared_fascicolo(text) from public;
grant execute on function public.smartbuy_shared_fascicolo(text) to anon, authenticated;

create or replace function public.smartbuy_shared_document_path(p_token text, p_document_id bigint)
returns text
language sql
stable
security definer
set search_path = public, extensions
as $$
  select d.storage_path
  from documents d
  join properties p on p.id::text = d.fascicolo_id
  where p.share_token = p_token and p.share_enabled = true and d.id = p_document_id
  limit 1;
$$;

revoke execute on function public.smartbuy_shared_document_path(text, bigint) from public;
grant execute on function public.smartbuy_shared_document_path(text, bigint) to anon, authenticated;
