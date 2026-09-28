alter table public.properties drop constraint if exists properties_typology_check;
alter table public.properties add constraint properties_typology_check
  check (typology in ('appartamento', 'villa', 'box', 'negozio', 'ufficio', 'capannone', 'magazzino', 'centro_commerciale'));

alter table public.properties add column if not exists canone_mensile_eur numeric;
