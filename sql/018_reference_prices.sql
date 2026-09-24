-- Zone price lists published by third parties, used next to OMI.
-- First source: FIAIP Bologna, "Prezzi e tendenze del mercato immobiliare"
-- (Bologna città, 51 zones), loaded from reference/fiaip_bologna_<year>.json.
-- item: abitazioni_nuovo | abitazioni_ristrutturato | abitazioni_buono | abitazioni_da_ristrutturare |
--       uffici_* | negozi_* (eur/m2), box_* | posto_auto_* (eur a corpo), affitto_* (see unit).

create table if not exists public.reference_prices (
  source text not null,
  year smallint not null,
  comune_cat text not null,
  zone_code text not null,
  zone_name text not null,
  item text not null,
  min_value numeric,
  max_value numeric,
  unit text not null,
  loaded_at timestamptz not null default now(),
  primary key (source, year, comune_cat, zone_code, item)
);

alter table public.reference_prices enable row level security;
drop policy if exists read_all on public.reference_prices;
create policy read_all on public.reference_prices for select to authenticated using (true);
grant select on public.reference_prices to authenticated;
grant select, insert, update, delete on public.reference_prices to service_role;

-- The FIAIP zone of a property is chosen by the agent (FIAIP publishes no digital boundaries).
alter table public.properties add column if not exists fiaip_zone text;
