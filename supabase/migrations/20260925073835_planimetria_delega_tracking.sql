-- Agent's own note that the signed Mod. 12T-AgIm delega (planimetria access,
-- free channel) was sent to Agenzia delle Entrate, so the app can remind them
-- of the 30-day submission deadline from the owner's signature. Purely
-- informational: unlike delega_confirmed_at (021_delega.sql) it gates nothing.

alter table public.properties add column if not exists planimetria_delega_sent_at timestamptz;
