-- New commercial typology "centro_commerciale" (OMI cod_tip 17, quotations
-- already loaded in omi_quotes) and a manual monthly rent field for the
-- reddituale valuation method, so it works before any lease is uploaded and
-- analysed. canone_mensile_eur is only meaningful for commercial typologies;
-- the frontend hides the field for residenziale ones.

alter table public.properties drop constraint if exists properties_typology_check;
alter table public.properties add constraint properties_typology_check
  check (typology in ('appartamento', 'villa', 'box', 'negozio', 'ufficio', 'capannone', 'magazzino', 'centro_commerciale'));

alter table public.properties add column if not exists canone_mensile_eur numeric;
