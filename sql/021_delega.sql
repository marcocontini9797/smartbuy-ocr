-- Confirmation that the agent holds a delega/incarico from the owner before
-- SmartBuy requests cadastral or land-registry data on their behalf (Catasto,
-- Conservatoria). Gates api/registry_routes.py, not a legal record itself:
-- the real delega stays with the agent (signed PDF), this only unlocks the flow.

alter table public.properties add column if not exists delega_confirmed_at timestamptz;
