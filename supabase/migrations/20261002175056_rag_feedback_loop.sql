create table public.agent_retrieval_traces (
  id uuid primary key default gen_random_uuid(),
  property_id bigint not null references public.properties(id) on delete cascade,
  user_id uuid not null default auth.uid(),
  question text not null check (char_length(question) between 1 and 1000),
  question_embedding extensions.vector(1536),
  strength text not null,
  best_relevance real,
  best_similarity real,
  chunk_ids uuid[] not null default '{}',
  created_at timestamptz not null default now()
);

create index agent_retrieval_traces_property_idx on public.agent_retrieval_traces (property_id, created_at desc);

alter table public.agent_retrieval_traces enable row level security;
create policy agent_retrieval_traces_select on public.agent_retrieval_traces
  for select to authenticated using (private.owns_property(property_id));
create policy agent_retrieval_traces_insert on public.agent_retrieval_traces
  for insert to authenticated with check (private.owns_property(property_id) and user_id = auth.uid());
grant select, insert on public.agent_retrieval_traces to authenticated;
grant all on public.agent_retrieval_traces to service_role;

alter table public.agent_answer_feedback
  add column trace_id uuid references public.agent_retrieval_traces(id) on delete set null;

drop policy agent_answer_feedback_insert on public.agent_answer_feedback;
create policy agent_answer_feedback_insert on public.agent_answer_feedback
  for insert to authenticated with check (
    private.owns_property(property_id) and user_id = auth.uid()
    and (trace_id is null or exists (
      select 1 from public.agent_retrieval_traces t where t.id = trace_id and t.property_id = agent_answer_feedback.property_id))
  );

create or replace function public.smartbuy_feedback_hints(
  p_property_id bigint, p_embedding extensions.vector(1536), p_min_similarity double precision default 0.88)
returns table (chunk_id uuid, rating smallint, similarity double precision)
language sql stable security invoker
set search_path = public, extensions, pg_temp
as $$
  select c, f.rating, 1 - (t.question_embedding <=> p_embedding)
  from public.agent_answer_feedback f
  join public.agent_retrieval_traces t on t.id = f.trace_id
  cross join lateral unnest(t.chunk_ids) as c
  where f.property_id = p_property_id and t.property_id = p_property_id
    and t.question_embedding is not null
    and 1 - (t.question_embedding <=> p_embedding) >= p_min_similarity
$$;

revoke execute on function public.smartbuy_feedback_hints(bigint, extensions.vector, double precision) from public, anon;
grant execute on function public.smartbuy_feedback_hints(bigint, extensions.vector, double precision) to authenticated, service_role;

notify pgrst, 'reload schema';
