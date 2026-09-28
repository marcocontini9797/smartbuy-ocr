alter table public.properties add column if not exists workflow_context jsonb not null default '{}'::jsonb;
alter table public.properties add constraint properties_workflow_context_object check (jsonb_typeof(workflow_context) = 'object');
alter table public.properties drop constraint if exists properties_typology_check;
alter table public.properties add constraint properties_typology_check check (typology in ('appartamento','villa','box','negozio','ufficio','capannone','laboratorio','magazzino','centro_commerciale'));
comment on column public.properties.workflow_context is 'Agent-declared workflow answers; unknown is not an exemption or official verification.';
