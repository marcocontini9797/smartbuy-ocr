create table if not exists public.market_volumes (
  provincia text not null,
  capoluogo boolean not null,
  series text not null,
  area text,
  regione text,
  ntn jsonb not null default '{}'::jsonb,
  ntn_provisional jsonb not null default '{}'::jsonb,
  surface jsonb not null default '{}'::jsonb,
  source text not null,
  loaded_at timestamptz not null default now(),
  primary key (provincia, capoluogo, series)
);
create table if not exists public.istat_comuni (
  codice_catastale text primary key,
  codice_istat text not null,
  nome text not null,
  sigla_provincia text not null,
  regione text not null,
  capoluogo boolean not null,
  loaded_at timestamptz not null default now()
);
create index if not exists istat_comuni_nome_idx on public.istat_comuni (upper(nome));
alter table public.market_volumes enable row level security;
alter table public.istat_comuni enable row level security;
drop policy if exists read_all on public.market_volumes;
create policy read_all on public.market_volumes for select to authenticated using (true);
drop policy if exists read_all on public.istat_comuni;
create policy read_all on public.istat_comuni for select to authenticated using (true);
grant select on public.market_volumes, public.istat_comuni to authenticated;
