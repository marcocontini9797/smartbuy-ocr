-- An agent can mark a document as replaced by a newer version of it. Nothing is
-- deleted: the row, its file and its facts stay, and the mark can be undone.
alter table public.documents
    add column if not exists superseded_by bigint references public.documents(id) on delete set null,
    add column if not exists superseded_at timestamptz;

alter table public.documents
    add constraint documents_not_self_superseded
    check (superseded_by is null or superseded_by <> id);

create index if not exists documents_superseded_by_idx
    on public.documents (superseded_by)
    where superseded_by is not null;

comment on column public.documents.superseded_by is
    'Id of the newer version that replaces this document in the fascicolo checks; null while this document is current.';
