CREATE TABLE participants (
    id integer primary key autoincrement not null,
    userhash text not null,
    sex text not null,
    age integer not null,
    handedness text not null,
    created text not null
);

CREATE TABLE trials (
    id integer primary key autoincrement not null,
    participant_id integer not null references participants(id),
    practicing text not null,
    block_num integer not null,
    trial_num integer not null,
    array_location text not null,
    target_trial text not null,
    target_jitter text not null,
    practice_performance text not null,
    rt text not null,
    correct integer not null
);
