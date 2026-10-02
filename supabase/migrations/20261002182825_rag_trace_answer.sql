alter table public.agent_retrieval_traces
  add column answer text check (answer is null or char_length(answer) <= 8000),
  add column answer_grounded boolean;

create policy agent_retrieval_traces_update on public.agent_retrieval_traces
  for update to authenticated using (private.owns_property(property_id) and user_id = auth.uid())
  with check (private.owns_property(property_id) and user_id = auth.uid());
grant update (answer, answer_grounded) on public.agent_retrieval_traces to authenticated;

notify pgrst, 'reload schema';
