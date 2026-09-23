-- Bounding box [min_lon, min_lat, max_lon, max_lat] of a municipality from its
-- OMI zones, used to constrain geocoding to the right town (Nominatim otherwise
-- matches "Bologna" as a province and returns streets of nearby towns).
create or replace function public.smartbuy_comune_bbox(p_city text)
returns jsonb
language sql
stable
security definer
set search_path = public, extensions
as $$
  select case when e is null then null
         else jsonb_build_array(ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e)) end
  from (
    select ST_Extent(z.geom)::geometry as e
    from omi_zones z
    where z.comune_cat in (
      select distinct q.comune_amm from omi_quotes q
      where regexp_replace(upper(q.comune_descrizione), '[^A-Z]', '', 'g')
          = regexp_replace(upper(p_city), '[^A-Z]', '', 'g')
    )
  ) s;
$$;

revoke execute on function public.smartbuy_comune_bbox(text) from public, anon;
grant execute on function public.smartbuy_comune_bbox(text) to authenticated;
