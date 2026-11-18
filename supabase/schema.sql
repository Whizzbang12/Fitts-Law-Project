-- Run this once in the Supabase SQL editor.
-- The website may insert through these functions only.
-- It cannot read other participants' rows.
-- Your download script uses the service role key, which stays off GitHub.

create table if not exists session_counters (
    mode text primary key,
    next_number integer not null
);

create table if not exists sessions (
    mode text not null check (mode in ('participant', 'test')),
    session_number integer not null,
    token uuid not null,
    excluded boolean not null default false,
    os_name text,
    os_release text,
    os_version text,
    machine text,
    screen_width integer,
    screen_height integer,
    scale double precision,
    primary key (mode, session_number)
);

create table if not exists trials (
    id bigint generated always as identity primary key,
    mode text not null,
    session_number integer not null,
    trial_number integer not null,
    target_number integer not null,
    direction text not null,
    distance_px double precision not null,
    diameter_px double precision not null,
    id_bits double precision not null,
    mt_ms double precision not null,
    path_length_px double precision not null,
    hit integer not null,
    error_distance_px double precision not null,
    scale double precision not null,
    path_length_raw_px double precision,
    error_distance_raw_px double precision
);

create table if not exists demographics (
    session_number integer primary key,
    name text,
    gender text,
    gender_other text,
    age text,
    handedness text,
    computer_hours text,
    input_device text,
    input_device_other text,
    mouse_model text,
    machine_company text,
    disabilities text,
    location text,
    location_other text,
    distraction integer,
    skipped_questions text,
    survey_back_count integer
);

alter table sessions enable row level security;
alter table trials enable row level security;
alter table demographics enable row level security;
alter table session_counters enable row level security;

create or replace function claim_session(p_mode text)
returns table(session_number integer, token uuid)
language plpgsql
security definer
set search_path = public
as $$
declare
    assigned integer;
    issued uuid;
begin
    if p_mode not in ('participant', 'test') then
        raise exception 'invalid mode';
    end if;
    insert into session_counters (mode, next_number)
    values (p_mode, 2)
    on conflict (mode) do update
        set next_number = session_counters.next_number + 1
    returning session_counters.next_number - 1 into assigned;
    issued := gen_random_uuid();
    insert into sessions (mode, session_number, token)
    values (p_mode, assigned, issued);
    return query select assigned, issued;
end;
$$;

create or replace function abandon_session(p_mode text, p_session integer, p_token uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if not exists (
        select 1 from sessions
        where mode = p_mode and session_number = p_session and token = p_token
    ) then
        return;
    end if;
    if exists (
        select 1 from trials
        where mode = p_mode and session_number = p_session
    ) then
        return;
    end if;
    if p_mode = 'participant' and exists (
        select 1 from demographics where session_number = p_session
    ) then
        return;
    end if;
    delete from sessions
    where mode = p_mode and session_number = p_session and token = p_token;
    update session_counters
    set next_number = p_session
    where mode = p_mode and next_number = p_session + 1;
end;
$$;

create or replace function insert_trial(
    p_mode text,
    p_session integer,
    p_token uuid,
    p_trial integer,
    p_target integer,
    p_direction text,
    p_distance double precision,
    p_diameter double precision,
    p_id double precision,
    p_mt double precision,
    p_path double precision,
    p_hit integer,
    p_error double precision,
    p_scale double precision,
    p_path_raw double precision,
    p_error_raw double precision
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if not exists (
        select 1 from sessions
        where mode = p_mode and session_number = p_session and token = p_token
    ) then
        raise exception 'invalid session';
    end if;
    insert into trials (
        mode, session_number, trial_number, target_number, direction,
        distance_px, diameter_px, id_bits, mt_ms, path_length_px, hit,
        error_distance_px, scale, path_length_raw_px, error_distance_raw_px
    ) values (
        p_mode, p_session, p_trial, p_target, p_direction,
        p_distance, p_diameter, p_id, p_mt, p_path, p_hit,
        p_error, p_scale, p_path_raw, p_error_raw
    );
end;
$$;

create or replace function save_demographics(
    p_session integer,
    p_token uuid,
    p_name text,
    p_gender text,
    p_gender_other text,
    p_age text,
    p_handedness text,
    p_computer_hours text,
    p_input_device text,
    p_input_device_other text,
    p_mouse_model text,
    p_machine_company text,
    p_disabilities text,
    p_location text,
    p_location_other text,
    p_distraction integer,
    p_skipped text,
    p_back_count integer
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    if not exists (
        select 1 from sessions
        where mode = 'participant' and session_number = p_session and token = p_token
    ) then
        raise exception 'invalid session';
    end if;
    insert into demographics (
        session_number, name, gender, gender_other, age, handedness,
        computer_hours, input_device, input_device_other, mouse_model,
        machine_company, disabilities, location, location_other, distraction,
        skipped_questions, survey_back_count
    ) values (
        p_session, p_name, p_gender, p_gender_other, p_age, p_handedness,
        p_computer_hours, p_input_device, p_input_device_other, p_mouse_model,
        p_machine_company, p_disabilities, p_location, p_location_other, p_distraction,
        p_skipped, p_back_count
    )
    on conflict (session_number) do update set
        name = excluded.name,
        gender = excluded.gender,
        gender_other = excluded.gender_other,
        age = excluded.age,
        handedness = excluded.handedness,
        computer_hours = excluded.computer_hours,
        input_device = excluded.input_device,
        input_device_other = excluded.input_device_other,
        mouse_model = excluded.mouse_model,
        machine_company = excluded.machine_company,
        disabilities = excluded.disabilities,
        location = excluded.location,
        location_other = excluded.location_other,
        distraction = excluded.distraction,
        skipped_questions = excluded.skipped_questions,
        survey_back_count = excluded.survey_back_count;
end;
$$;

create or replace function save_session_info(
    p_mode text,
    p_session integer,
    p_token uuid,
    p_os_name text,
    p_os_release text,
    p_os_version text,
    p_machine text,
    p_width integer,
    p_height integer,
    p_scale double precision
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    update sessions
    set os_name = p_os_name,
        os_release = p_os_release,
        os_version = p_os_version,
        machine = p_machine,
        screen_width = p_width,
        screen_height = p_height,
        scale = p_scale
    where mode = p_mode and session_number = p_session and token = p_token;
    if not found then
        raise exception 'invalid session';
    end if;
end;
$$;

revoke all on function claim_session(text) from public;
revoke all on function abandon_session(text, integer, uuid) from public;
revoke all on function insert_trial(text, integer, uuid, integer, integer, text, double precision, double precision, double precision, double precision, double precision, integer, double precision, double precision, double precision, double precision) from public;
revoke all on function save_demographics(integer, uuid, text, text, text, text, text, text, text, text, text, text, text, text, text, integer, text, integer) from public;
revoke all on function save_session_info(text, integer, uuid, text, text, text, text, integer, integer, double precision) from public;

grant execute on function claim_session(text) to anon, authenticated;
grant execute on function abandon_session(text, integer, uuid) to anon, authenticated;
grant execute on function insert_trial(text, integer, uuid, integer, integer, text, double precision, double precision, double precision, double precision, double precision, integer, double precision, double precision, double precision, double precision) to anon, authenticated;
grant execute on function save_demographics(integer, uuid, text, text, text, text, text, text, text, text, text, text, text, text, text, integer, text, integer) to anon, authenticated;
grant execute on function save_session_info(text, integer, uuid, text, text, text, text, integer, integer, double precision) to anon, authenticated;

-- To leave someone out of Excel without deleting them or changing later numbers:
--   update sessions set excluded = true where mode = 'participant' and session_number = 4;
