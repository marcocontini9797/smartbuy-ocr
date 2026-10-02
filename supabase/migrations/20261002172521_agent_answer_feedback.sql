create table public.agent_answer_feedback (
  id uuid primary key default gen_random_uuid(),
  property_id bigint not null references public.properties(id) on delete cascade,
  user_id uuid not null default auth.uid(),
  question text not null check (char_length(question) between 1 and 1000),
  answer text not null check (char_length(answer) <= 8000),
  rating smallint not null check (rating in (-1, 1)),
  comment text check (comment is null or char_length(comment) <= 1000),
  grounded boolean,
  sources jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now()
);

create index agent_answer_feedback_created_idx on public.agent_answer_feedback (created_at desc);
create index agent_answer_feedback_property_idx on public.agent_answer_feedback (property_id);

alter table public.agent_answer_feedback enable row level security;

create policy agent_answer_feedback_select on public.agent_answer_feedback
  for select to authenticated using (private.owns_property(property_id));
create policy agent_answer_feedback_insert on public.agent_answer_feedback
  for insert to authenticated with check (private.owns_property(property_id) and user_id = auth.uid());

grant select, insert on public.agent_answer_feedback to authenticated;
grant all on public.agent_answer_feedback to service_role;

notify pgrst, 'reload schema';
