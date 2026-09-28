create table if not exists public.seller_leads (
  id uuid primary key default gen_random_uuid(),
  email text,
  address text,
  city text,
  answers jsonb not null,
  estimate jsonb,
  complexity jsonb,
  report text,
  created_at timestamptz not null default now()
);

-- RLS enabled with no policies: only the service-role backend ever reads or
-- writes this table (anonymous quiz submissions, agent-facing lead review) —
-- neither anon nor authenticated should have direct table access.
alter table public.seller_leads enable row level security;
