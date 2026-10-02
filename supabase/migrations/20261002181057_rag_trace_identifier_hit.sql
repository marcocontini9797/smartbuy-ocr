alter table public.agent_retrieval_traces add column identifier_hit boolean not null default false;
notify pgrst, 'reload schema';
