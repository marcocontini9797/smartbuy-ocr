create table if not exists public.seismic_zones (
  codice_istat text primary key,
  comune text not null,
  sigla_provincia text,
  zona text not null,
  source text not null default 'Dipartimento della Protezione Civile - classificazione sismica, maggio 2025',
  loaded_at timestamptz not null default now()
);
create table if not exists public.municipal_hazard (
  codice_istat text primary key,
  comune text not null,
  area_kmq numeric,
  popolazione_2021 integer,
  flood_area_p3_pct numeric, flood_area_p2_pct numeric, flood_area_p1_pct numeric,
  flood_pop_p3_pct numeric, flood_pop_p2_pct numeric,
  flood_buildings_p3_pct numeric, flood_buildings_p2_pct numeric,
  landslide_area_p4_pct numeric, landslide_area_p3_pct numeric, landslide_area_p2_pct numeric,
  landslide_area_p1_pct numeric, landslide_area_aa_pct numeric,
  landslide_pop_p3p4_pct numeric, landslide_buildings_p3p4_pct numeric,
  source text not null default 'ISPRA IdroGEO - indicatori di rischio (mosaicature frane 2024, alluvioni 2020)',
  loaded_at timestamptz not null default now()
);
create table if not exists public.irpef_incomes (
  anno smallint not null,
  codice_catastale text not null,
  cap text not null default '',
  comune text not null,
  contribuenti integer,
  reddito_imponibile_eur numeric,
  reddito_imponibile_medio_eur numeric,
  reddito_complessivo_freq integer,
  reddito_complessivo_eur numeric,
  reddito_fabbricati_freq integer,
  reddito_fabbricati_eur numeric,
  source text not null default 'MEF - Dipartimento delle Finanze, dichiarazioni IRPEF',
  loaded_at timestamptz not null default now(),
  primary key (anno, codice_catastale, cap)
);
create table if not exists public.house_price_index (
  ref_area text not null,
  purchase text not null,
  period text not null,
  index_2025 numeric,
  qoq_pct numeric,
  yoy_pct numeric,
  provisional boolean not null default false,
  source text not null default 'Istat - Prezzi delle abitazioni (IPAB), base 2025=100',
  loaded_at timestamptz not null default now(),
  primary key (ref_area, purchase, period)
);
create table if not exists public.property_hazards (
  property_id bigint primary key references public.properties(id) on delete cascade,
  latitude double precision not null,
  longitude double precision not null,
  flood_level smallint,
  landslide_level smallint,
  details jsonb not null default '{}'::jsonb,
  checked_at timestamptz not null default now()
);
alter table public.seismic_zones enable row level security;
alter table public.municipal_hazard enable row level security;
alter table public.irpef_incomes enable row level security;
alter table public.house_price_index enable row level security;
alter table public.property_hazards enable row level security;
drop policy if exists read_all on public.seismic_zones;
create policy read_all on public.seismic_zones for select to authenticated using (true);
drop policy if exists read_all on public.municipal_hazard;
create policy read_all on public.municipal_hazard for select to authenticated using (true);
drop policy if exists read_all on public.irpef_incomes;
create policy read_all on public.irpef_incomes for select to authenticated using (true);
drop policy if exists read_all on public.house_price_index;
create policy read_all on public.house_price_index for select to authenticated using (true);
drop policy if exists owner_all on public.property_hazards;
create policy owner_all on public.property_hazards for all to authenticated
  using (private.owns_property(property_id)) with check (private.owns_property(property_id));
grant select on public.seismic_zones, public.municipal_hazard, public.irpef_incomes, public.house_price_index to authenticated;
grant select, insert, update, delete on public.property_hazards to authenticated;
grant select, insert, update, delete on public.seismic_zones, public.municipal_hazard, public.irpef_incomes,
  public.house_price_index to service_role;
create index if not exists istat_comuni_codice_istat_idx on public.istat_comuni (codice_istat);
