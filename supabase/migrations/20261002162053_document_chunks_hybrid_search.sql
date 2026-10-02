-- Persistent retrieval index of the OCR text of each document: one row per chunk,
-- with its pages, a short deterministic context, an embedding and an Italian
-- full-text vector. Replaces rebuilding an in-memory index per request.
create extension if not exists vector with schema extensions;

-- unaccent() is only STABLE, which a generated column refuses; the wrapper pins it.
create or replace function public.immutable_unaccent(text)
returns text
language sql
immutable
parallel safe
strict
set search_path = extensions, public
as $$ select extensions.unaccent('extensions.unaccent'::regdictionary, $1) $$;

create table public.document_chunks (
    id uuid primary key default gen_random_uuid(),
    property_id bigint not null references public.properties(id) on delete cascade,
    document_id bigint not null references public.documents(id) on delete cascade,
    chunk_index integer not null,
    page_start integer not null,
    page_end integer not null,
    heading text,
    content text not null,
    context text not null default '',
    embedding extensions.vector(1536),
    embedding_model text,
    content_hash text not null,
    fts tsvector generated always as (
        to_tsvector('italian', public.immutable_unaccent(coalesce(context, '') || ' ' || content))
    ) stored,
    created_at timestamptz not null default now(),
    unique (document_id, chunk_index)
);

create index document_chunks_property_idx on public.document_chunks (property_id, document_id);
create index document_chunks_fts_idx on public.document_chunks using gin (fts);

alter table public.document_chunks enable row level security;

create policy document_chunks_owner_select on public.document_chunks
    for select to authenticated
    using (private.owns_property(property_id));

create policy document_chunks_owner_insert on public.document_chunks
    for insert to authenticated
    with check (
        private.owns_property(property_id)
        and exists (
            select 1 from public.documents d
            where d.id = document_chunks.document_id and d.fascicolo_id = document_chunks.property_id::text
        )
    );

create policy document_chunks_owner_delete on public.document_chunks
    for delete to authenticated
    using (private.owns_property(property_id));

grant select, insert, delete on public.document_chunks to authenticated;
grant all on public.document_chunks to service_role;

-- Hybrid search of one property: the nearest chunks by embedding and the best
-- matches of the Italian full-text query, each with its rank. The caller fuses
-- the ranks (and several phrasings of the question). Runs as the caller, so
-- row level security scopes it; replaced versions of a document are left out.
create or replace function public.smartbuy_search_chunks(
    p_property_id bigint,
    p_embedding extensions.vector(1536),
    p_query text,
    p_limit integer default 24
)
returns table (
    chunk_id uuid, document_id bigint, document_name text, document_type text,
    chunk_index integer, page_start integer, page_end integer, heading text,
    content text, context text, similarity double precision, sem_rank integer, lex_rank integer
)
language plpgsql
stable
security invoker
set search_path = public, extensions
as $$
#variable_conflict use_column
declare
    q tsquery;
begin
    begin
        q := to_tsquery('italian', public.immutable_unaccent(coalesce(p_query, '')));
    exception when others then
        q := null;
    end;
    return query
    with scoped as (
        select c.id, c.document_id, d.file_name, d.document_type, c.chunk_index, c.page_start, c.page_end,
               c.heading, c.content, c.context, c.embedding, c.fts
        from public.document_chunks c
        join public.documents d on d.id = c.document_id
        where c.property_id = p_property_id and d.superseded_by is null and c.embedding is not null
    ),
    sem as (
        select s.id, (row_number() over (order by s.embedding <=> p_embedding))::integer as r
        from scoped s order by s.embedding <=> p_embedding limit p_limit
    ),
    lex as (
        select s.id, (row_number() over (order by ts_rank_cd(s.fts, q) desc))::integer as r
        from scoped s where q is not null and s.fts @@ q
        order by ts_rank_cd(s.fts, q) desc limit p_limit
    )
    select s.id, s.document_id, s.file_name, s.document_type, s.chunk_index, s.page_start, s.page_end,
           s.heading, s.content, s.context, (1 - (s.embedding <=> p_embedding))::double precision,
           sem.r, lex.r
    from scoped s
    left join sem on sem.id = s.id
    left join lex on lex.id = s.id
    where sem.id is not null or lex.id is not null;
end;
$$;

revoke execute on function public.smartbuy_search_chunks(bigint, extensions.vector, text, integer) from public, anon;
grant execute on function public.smartbuy_search_chunks(bigint, extensions.vector, text, integer) to authenticated, service_role;
