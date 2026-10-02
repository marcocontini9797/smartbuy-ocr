alter table public.agent_retrieval_traces
  add column candidates jsonb not null default '[]'::jsonb,
  add column config_version integer;

create table public.rag_configs (
  id serial primary key,
  params jsonb not null default '{}'::jsonb,
  status text not null check (status in ('active', 'retired', 'rejected')),
  parent_id integer references public.rag_configs(id),
  reason text,
  metrics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  activated_at timestamptz
);
create unique index rag_configs_one_active on public.rag_configs ((status)) where status = 'active';
alter table public.rag_configs enable row level security;
create policy rag_configs_read_active on public.rag_configs for select to authenticated using (status = 'active');
grant select on public.rag_configs to authenticated;
grant all on public.rag_configs to service_role;
grant usage, select on sequence public.rag_configs_id_seq to service_role;
insert into public.rag_configs (params, status, reason, activated_at) values ('{}'::jsonb, 'active', 'default parameters', now());

create table public.rag_feedback_labels (
  id uuid primary key default gen_random_uuid(),
  trace_id uuid not null references public.agent_retrieval_traces(id) on delete cascade,
  feedback_id uuid references public.agent_answer_feedback(id) on delete set null,
  source text not null check (source in ('explicit', 'implicit_reask')),
  user_id uuid,
  rating smallint not null check (rating in (-1, 1)),
  weight real not null default 0,
  verdict text not null check (verdict in ('accepted', 'review', 'rejected')),
  judge_supported boolean,
  reasons jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  unique (trace_id, source)
);
create index rag_feedback_labels_user_idx on public.rag_feedback_labels (user_id, created_at desc);
alter table public.rag_feedback_labels enable row level security;
grant all on public.rag_feedback_labels to service_role;

notify pgrst, 'reload schema';
