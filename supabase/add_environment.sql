-- Run this once in the Supabase SQL editor for the project that is already live.
-- It adds the place and distraction answers without removing existing rows.

alter table demographics add column if not exists location text;
alter table demographics add column if not exists location_other text;
alter table demographics add column if not exists distraction integer;

drop function if exists save_demographics(integer, uuid, text, text, text, text, text, text, text, text, text, text, text, text, integer);

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

revoke all on function save_demographics(integer, uuid, text, text, text, text, text, text, text, text, text, text, text, text, text, integer, text, integer) from public;
grant execute on function save_demographics(integer, uuid, text, text, text, text, text, text, text, text, text, text, text, text, text, integer, text, integer) to anon, authenticated;
