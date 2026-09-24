-- What the property is (typology) and what the agent is handling (sale or lease).
-- property_type (residenziale | commerciale) stays as the asset class and is
-- derived from the typology by the API.

alter table public.properties add column if not exists typology text;
alter table public.properties add column if not exists contract text not null default 'vendita';

update public.properties
   set typology = case when property_type = 'commerciale' then 'negozio' else 'appartamento' end
 where typology is null;

alter table public.properties alter column typology set default 'appartamento';
alter table public.properties alter column typology set not null;

alter table public.properties drop constraint if exists properties_typology_check;
alter table public.properties add constraint properties_typology_check
  check (typology in ('appartamento', 'villa', 'box', 'negozio', 'ufficio', 'capannone', 'magazzino'));
alter table public.properties drop constraint if exists properties_contract_check;
alter table public.properties add constraint properties_contract_check check (contract in ('vendita', 'affitto'));
