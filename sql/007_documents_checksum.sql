-- The same file uploaded twice must not count as two independent sources in
-- cross-validation: keep its SHA-256 to reject duplicates per property.
alter table public.documents add column if not exists content_sha256 text;
create index if not exists documents_fascicolo_checksum_idx
  on public.documents (fascicolo_id, content_sha256);
