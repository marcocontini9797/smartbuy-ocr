create table if not exists public.smartbuy_public_rate_limits (
    scope text not null,
    subject_hash text not null,
    window_start timestamptz not null,
    window_seconds integer not null check (window_seconds > 0),
    request_count integer not null default 0 check (request_count >= 0),
    updated_at timestamptz not null default now(),
    primary key (
        scope,
        subject_hash,
        window_start,
        window_seconds
    )
);

alter table public.smartbuy_public_rate_limits
    enable row level security;

revoke all on public.smartbuy_public_rate_limits
from public, anon, authenticated;

grant select, insert, update, delete
on public.smartbuy_public_rate_limits
to service_role;

create or replace function public.smartbuy_consume_public_rate_limit(
    p_scope text,
    p_subject_hash text,
    p_window_seconds integer,
    p_limit integer
)
returns jsonb
language plpgsql
security invoker
set search_path = public
as $$
declare
    v_now timestamptz := clock_timestamp();
    v_epoch bigint;
    v_window_epoch bigint;
    v_window_start timestamptz;
    v_count integer;
    v_retry_after integer;
begin
    if p_scope is null or length(p_scope) < 1 or length(p_scope) > 100 then
        raise exception 'invalid_scope';
    end if;

    if p_subject_hash is null
       or p_subject_hash !~ '^[0-9a-f]{64}$' then
        raise exception 'invalid_subject_hash';
    end if;

    if p_window_seconds < 1 or p_window_seconds > 86400 then
        raise exception 'invalid_window';
    end if;

    if p_limit < 1 or p_limit > 10000 then
        raise exception 'invalid_limit';
    end if;

    v_epoch := floor(extract(epoch from v_now));

    v_window_epoch :=
        (v_epoch / p_window_seconds) * p_window_seconds;

    v_window_start :=
        to_timestamp(v_window_epoch);

    insert into public.smartbuy_public_rate_limits (
        scope,
        subject_hash,
        window_start,
        window_seconds,
        request_count,
        updated_at
    )
    values (
        p_scope,
        p_subject_hash,
        v_window_start,
        p_window_seconds,
        1,
        v_now
    )
    on conflict (
        scope,
        subject_hash,
        window_start,
        window_seconds
    )
    do update
    set
        request_count =
            public.smartbuy_public_rate_limits.request_count + 1,
        updated_at = v_now
    returning request_count into v_count;

    v_retry_after := greatest(
        1,
        ceil(
            extract(
                epoch from (
                    v_window_start
                    + make_interval(secs => p_window_seconds)
                    - v_now
                )
            )
        )::integer
    );

    return jsonb_build_object(
        'allowed', v_count <= p_limit,
        'count', v_count,
        'limit', p_limit,
        'retry_after', v_retry_after
    );
end;
$$;

revoke execute on function
public.smartbuy_consume_public_rate_limit(
    text,
    text,
    integer,
    integer
)
from public, anon, authenticated;

grant execute on function
public.smartbuy_consume_public_rate_limit(
    text,
    text,
    integer,
    integer
)
to service_role;