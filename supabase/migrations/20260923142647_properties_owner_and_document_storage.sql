alter table public.properties alter column user_id set default auth.uid();

alter table public.documents add column if not exists storage_path text;

drop policy if exists "smartbuy documents owner read" on storage.objects;
drop policy if exists "smartbuy documents owner insert" on storage.objects;
drop policy if exists "smartbuy documents owner delete" on storage.objects;
create policy "smartbuy documents owner read" on storage.objects for select to authenticated
  using (bucket_id = 'smartbuy-documents' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "smartbuy documents owner insert" on storage.objects for insert to authenticated
  with check (bucket_id = 'smartbuy-documents' and (storage.foldername(name))[1] = (select auth.uid())::text);
create policy "smartbuy documents owner delete" on storage.objects for delete to authenticated
  using (bucket_id = 'smartbuy-documents' and (storage.foldername(name))[1] = (select auth.uid())::text);
