create table if not exists public.property_registry_checks (
  id uuid primary key default gen_random_uuid(),
  property_id bigint not null references public.properties(id) on delete cascade,
  kind text not null check (kind in ('immobili', 'prospetto', 'visura_pdf', 'ispezione')),
  environment text not null check (environment in ('sandbox', 'production')),
  request_id text,
  status text not null check (status in ('pending', 'done', 'error')),
  params jsonb not null default '{}'::jsonb,
  result jsonb,
  document_id bigint,
  cost_eur numeric,
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists property_registry_checks_property_idx on public.property_registry_checks (property_id, created_at desc);
alter table public.property_registry_checks enable row level security;
drop policy if exists owner_all on public.property_registry_checks;
create policy owner_all on public.property_registry_checks for all to authenticated
  using (private.owns_property(property_id)) with check (private.owns_property(property_id));
grant select, insert, update, delete on public.property_registry_checks to authenticated;
