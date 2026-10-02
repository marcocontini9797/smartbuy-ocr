-- The extracted text of a document is readable and writable only by the owner
-- of the document, through the same ownership rule as `documents` itself.
grant select, insert on public.document_text_extractions to authenticated;

create policy document_texts_owner_select on public.document_text_extractions
    for select to authenticated
    using (exists (
        select 1 from public.documents d
        where d.id = document_text_extractions.document_id
    ));

create policy document_texts_owner_insert on public.document_text_extractions
    for insert to authenticated
    with check (exists (
        select 1 from public.documents d
        where d.id = document_text_extractions.document_id
          and d.agente_id = (select auth.uid())::text
    ));

create unique index if not exists document_text_extractions_document_id_key
    on public.document_text_extractions (document_id);
