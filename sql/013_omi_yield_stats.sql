-- Market gross yield implied by OMI quotations (annual rent / price, mid values),
-- as quartiles over the zones of the municipality. Falls back to the province
-- and then to Italy when the municipality has fewer than 8 usable quotations.
create or replace function public.smartbuy_omi_yield_stats(p_comune_amm text, p_cod_tip text)
returns jsonb
language sql
stable
security invoker
set search_path = public
as $$
  with base as (
    select q.comune_amm, q.provincia, q.comune_descrizione,
           ((q.loc_min + q.loc_max) / 2 * 12) / ((q.compr_min + q.compr_max) / 2) as y
    from omi_quotes q
    where q.cod_tip = p_cod_tip and q.loc_min > 0 and q.loc_max > 0 and q.compr_min > 0 and q.compr_max > 0
  ),
  target as (select provincia, comune_descrizione from omi_quotes where comune_amm = p_comune_amm limit 1),
  scopes as (
    select 1 as rank, 'comune' as scope, (select comune_descrizione from target) as label, y from base where comune_amm = p_comune_amm
    union all
    select 2, 'provincia', (select provincia from target), y from base where provincia = (select provincia from target)
    union all
    select 3, 'italia', 'Italia', y from base
  ),
  stats as (
    select rank, scope, max(label) as label, count(*) as n,
           percentile_cont(0.25) within group (order by y) as p25,
           percentile_cont(0.5) within group (order by y) as p50,
           percentile_cont(0.75) within group (order by y) as p75
    from scopes group by rank, scope
  )
  select jsonb_build_object('scope', scope, 'label', label, 'n', n,
                            'p25', round(p25::numeric, 4), 'p50', round(p50::numeric, 4), 'p75', round(p75::numeric, 4))
  from stats where n >= 8 order by rank limit 1;
$$;

revoke execute on function public.smartbuy_omi_yield_stats(text, text) from public, anon;
grant execute on function public.smartbuy_omi_yield_stats(text, text) to authenticated;
