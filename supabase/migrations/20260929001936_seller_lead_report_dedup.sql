alter table public.seller_leads
    add column if not exists request_hash text;

alter table public.seller_leads
    add constraint seller_leads_request_hash_format
    check (
        request_hash is null
        or request_hash ~ '^[0-9a-f]{64}$'
    );

create index if not exists seller_leads_request_hash_created_at_idx
    on public.seller_leads (
        request_hash,
        created_at desc
    )
    where request_hash is not null;

comment on column public.seller_leads.request_hash is
    'Keyed SHA-256 hash used to reuse identical seller reports within the deduplication window.';