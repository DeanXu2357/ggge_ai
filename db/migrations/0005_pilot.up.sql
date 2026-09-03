CREATE TABLE pilot (
    stamp text NOT NULL,
    id bigint NOT NULL,
    name text NOT NULL,
    rarity integer NOT NULL,
    role integer NOT NULL,
    main_pilot bigint NOT NULL,
    is_playable boolean NOT NULL,
    PRIMARY KEY (stamp, id)
);

CREATE TABLE pilot_stat (
    stamp text NOT NULL,
    pilot_id bigint NOT NULL,
    stat text NOT NULL,
    base integer NOT NULL,
    max integer NOT NULL,
    sp_base integer NOT NULL,
    sp_max integer NOT NULL,
    PRIMARY KEY (stamp, pilot_id, stat),
    FOREIGN KEY (stamp, pilot_id) REFERENCES pilot (stamp, id) ON DELETE CASCADE,
    CHECK (stat IN ('ranged', 'melee', 'defense', 'reaction', 'awaken'))
);

CREATE TABLE pilot_tag (
    stamp text NOT NULL,
    pilot_id bigint NOT NULL,
    tag_id bigint NOT NULL,
    PRIMARY KEY (stamp, pilot_id, tag_id),
    FOREIGN KEY (stamp, pilot_id) REFERENCES pilot (stamp, id) ON DELETE CASCADE,
    FOREIGN KEY (stamp, tag_id) REFERENCES tag (stamp, id)
);

CREATE TABLE pilot_series (
    stamp text NOT NULL,
    pilot_id bigint NOT NULL,
    series_id bigint NOT NULL,
    sort integer NOT NULL,
    PRIMARY KEY (stamp, pilot_id, series_id),
    FOREIGN KEY (stamp, pilot_id) REFERENCES pilot (stamp, id) ON DELETE CASCADE
);

CREATE TABLE pilot_ability (
    stamp text NOT NULL,
    pilot_id bigint NOT NULL,
    sort integer NOT NULL,
    ability_id bigint NOT NULL,
    level integer NOT NULL,
    payload jsonb,
    PRIMARY KEY (stamp, pilot_id, sort),
    FOREIGN KEY (stamp, pilot_id) REFERENCES pilot (stamp, id) ON DELETE CASCADE
);

CREATE TABLE pilot_skill (
    stamp text NOT NULL,
    pilot_id bigint NOT NULL,
    sort integer NOT NULL,
    skill_id bigint NOT NULL,
    level integer NOT NULL,
    payload jsonb,
    PRIMARY KEY (stamp, pilot_id, sort),
    FOREIGN KEY (stamp, pilot_id) REFERENCES pilot (stamp, id) ON DELETE CASCADE
);
