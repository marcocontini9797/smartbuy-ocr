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
alter table public.properties add column if not exists fiaip_zone text;
