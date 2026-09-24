-- Comparables (listings or known sales) and real sale outcomes for calibration.

create table if not exists public.property_comparables (
  id uuid primary key default gen_random_uuid(),
  property_id bigint not null references public.properties(id) on delete cascade,
  kind text not null check (kind in ('annuncio', 'venduto')),
  source_url text,
  address text,
  surface_m2 numeric not null check (surface_m2 > 0),
  price numeric not null check (price > 0),
  condition text,
  floor integer,
  note text,
  observed_at date not null default current_date,
  created_at timestamptz not null default now()
);
create index if not exists property_comparables_property_idx on public.property_comparables (property_id);

-- One row per sold property: the actual price and the estimate SmartBuy had
-- produced, so estimate errors can be measured and corrected.
create table if not exists public.valuation_outcomes (
  property_id bigint primary key references public.properties(id) on delete cascade,
  user_id uuid not null default auth.uid(),
  property_type text not null,
  comune text,
  zona text,
  sale_price numeric not null check (sale_price > 0),
  sale_date date not null,
  estimate_low numeric,
  estimate_mid numeric,
  estimate_high numeric,
  created_at timestamptz not null default now()
);
create index if not exists valuation_outcomes_user_idx on public.valuation_outcomes (user_id, property_type);

alter table public.property_comparables enable row level security;
alter table public.valuation_outcomes enable row level security;
drop policy if exists owner_all on public.property_comparables;
create policy owner_all on public.property_comparables for all to authenticated
  using (private.owns_property(property_id)) with check (private.owns_property(property_id));
drop policy if exists owner_all on public.valuation_outcomes;
create policy owner_all on public.valuation_outcomes for all to authenticated
  using (user_id = (select auth.uid())) with check (user_id = (select auth.uid()) and private.owns_property(property_id));
grant select, insert, update, delete on public.property_comparables, public.valuation_outcomes to authenticated;

-- Zone lookup now also returns the OMI macro-area (for the negotiation discount).
create or replace function public.smartbuy_omi_zone_quotes(p_lat double precision, p_lon double precision)
returns jsonb
language sql
stable
security invoker
set search_path = public, extensions
as $$
  select jsonb_build_object(
    'comune_cat', z.comune_cat,
    'zona', z.zona,
    'fascia', z.fascia,
    'descrizione', z.descrizione,
    'semestre', z.semestre,
    'area_territoriale', (select q.area_territoriale from omi_quotes q where q.comune_amm = z.comune_cat limit 1),
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
