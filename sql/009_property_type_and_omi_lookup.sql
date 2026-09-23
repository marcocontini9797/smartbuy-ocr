-- Residential flat vs commercial unit: valued with different methods.
alter table public.properties
  add column if not exists property_type text not null default 'residenziale';
alter table public.properties drop constraint if exists properties_property_type_check;
alter table public.properties
  add constraint properties_property_type_check check (property_type in ('residenziale', 'commerciale'));

-- OMI zone containing a point, with every quotation of that zone.
-- OMI quotes join the zone polygons on comune_amm (cadastral code of the
-- municipality) + zona. OMI data is public; the function only reads it.
create or replace function public.smartbuy_omi_zone_quotes(p_lat double precision, p_lon double precision)
returns jsonb
language sql
stable
security definer
set search_path = public, extensions
as $$
  select jsonb_build_object(
    'comune_cat', z.comune_cat,
    'zona', z.zona,
    'fascia', z.fascia,
    'descrizione', z.descrizione,
    'semestre', z.semestre,
    'quotes', coalesce((
      select jsonb_agg(jsonb_build_object(
        'comune', q.comune_descrizione, 'cod_tip', q.cod_tip, 'tipologia', q.descr_tipologia, 'stato', q.stato,
        'compr_min', q.compr_min, 'compr_max', q.compr_max, 'loc_min', q.loc_min, 'loc_max', q.loc_max,
        'sup_compr', q.sup_nl_compr, 'sup_loc', q.sup_nl_loc, 'fascia', q.fascia, 'linkzona', q.linkzona))
      from omi_quotes q
      where q.comune_amm = z.comune_cat and q.zona = z.zona and q.semestre = z.semestre
    ), '[]'::jsonb)
  )
  from omi_zones z
  where ST_Contains(z.geom, ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326))
  order by z.semestre desc
  limit 1;
$$;

revoke execute on function public.smartbuy_omi_zone_quotes(double precision, double precision) from public, anon;
grant execute on function public.smartbuy_omi_zone_quotes(double precision, double precision) to authenticated;
