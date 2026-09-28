create table if not exists public.smartbuy_request_messages (
  property_id bigint not null references public.properties(id) on delete cascade,
  recipient_role text not null,
  message text not null,
  content_hash text not null,
  model text,
  generated_at timestamptz not null default now(),
  primary key (property_id, recipient_role)
);

alter table public.smartbuy_request_messages enable row level security;

create policy request_messages_owner on public.smartbuy_request_messages
  for all
  using (exists (select 1 from properties p where p.id = smartbuy_request_messages.property_id and p.user_id = (select auth.uid())))
  with check (exists (select 1 from properties p where p.id = smartbuy_request_messages.property_id and p.user_id = (select auth.uid())));
