CREATE TABLE tag (
    stamp text NOT NULL,
    id bigint NOT NULL,
    name text NOT NULL,
    PRIMARY KEY (stamp, id)
);

CREATE TABLE unit (
    stamp text NOT NULL,
    id bigint NOT NULL,
    name text NOT NULL,
    short_name text NOT NULL,
    rarity integer NOT NULL,
    role integer NOT NULL,
    area integer NOT NULL,
    body_type integer NOT NULL,
    series bigint NOT NULL,
    ult boolean NOT NULL,
    acquisition integer NOT NULL,
    main_unit bigint NOT NULL,
    defend boolean NOT NULL,
    evade boolean NOT NULL,
    PRIMARY KEY (stamp, id)
);

CREATE TABLE unit_tag (
    stamp text NOT NULL,
    unit_id bigint NOT NULL,
    tag_id bigint NOT NULL,
    PRIMARY KEY (stamp, unit_id, tag_id),
    FOREIGN KEY (stamp, unit_id) REFERENCES unit (stamp, id) ON DELETE CASCADE,
    FOREIGN KEY (stamp, tag_id) REFERENCES tag (stamp, id)
);

CREATE TABLE unit_series (
    stamp text NOT NULL,
    unit_id bigint NOT NULL,
    series_id bigint NOT NULL,
    sort integer NOT NULL,
    PRIMARY KEY (stamp, unit_id, series_id),
    FOREIGN KEY (stamp, unit_id) REFERENCES unit (stamp, id) ON DELETE CASCADE
);

CREATE TABLE unit_stat (
    stamp text NOT NULL,
    unit_id bigint NOT NULL,
    stat text NOT NULL,
    base integer NOT NULL,
    max integer NOT NULL,
    sp_base integer NOT NULL,
    sp_max integer NOT NULL,
    PRIMARY KEY (stamp, unit_id, stat),
    FOREIGN KEY (stamp, unit_id) REFERENCES unit (stamp, id) ON DELETE CASCADE,
    CHECK (stat IN ('hp', 'en', 'attack', 'defense', 'mobility', 'movement'))
);

CREATE TABLE unit_terrain (
    stamp text NOT NULL,
    unit_id bigint NOT NULL,
    terrain text NOT NULL,
    grade integer NOT NULL,
    PRIMARY KEY (stamp, unit_id, terrain),
    FOREIGN KEY (stamp, unit_id) REFERENCES unit (stamp, id) ON DELETE CASCADE,
    CHECK (terrain IN ('space', 'atmospheric', 'ground', 'surface', 'underwater'))
);

CREATE TABLE unit_ability (
    stamp text NOT NULL,
    unit_id bigint NOT NULL,
    sort integer NOT NULL,
    ability_id bigint NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (stamp, unit_id, sort),
    FOREIGN KEY (stamp, unit_id) REFERENCES unit (stamp, id) ON DELETE CASCADE
);

CREATE TABLE unit_ssp_stat (
    stamp text NOT NULL,
    unit_id bigint NOT NULL,
    stat text NOT NULL,
    base integer NOT NULL,
    max integer NOT NULL,
    PRIMARY KEY (stamp, unit_id, stat),
    FOREIGN KEY (stamp, unit_id) REFERENCES unit (stamp, id) ON DELETE CASCADE,
    CHECK (stat IN ('hp', 'en', 'attack', 'defense', 'mobility'))
);

-- Core level 0 is the initial release: the releases that the SSP
-- upgrade itself grants, before any core.
CREATE TABLE unit_ssp_core (
    stamp text NOT NULL,
    unit_id bigint NOT NULL,
    level integer NOT NULL,
    core_id bigint NOT NULL,
    release_point integer NOT NULL,
    PRIMARY KEY (stamp, unit_id, level),
    FOREIGN KEY (stamp, unit_id) REFERENCES unit (stamp, id) ON DELETE CASCADE
);

CREATE TABLE unit_ssp_release (
    stamp text NOT NULL,
    unit_id bigint NOT NULL,
    core_level integer NOT NULL,
    sort_order integer NOT NULL,
    kind text NOT NULL,
    target_id bigint NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (stamp, unit_id, core_level, sort_order),
    FOREIGN KEY (stamp, unit_id, core_level)
        REFERENCES unit_ssp_core (stamp, unit_id, level) ON DELETE CASCADE,
    CHECK (kind IN (
        'weapon_enhance', 'status_up', 'terrain',
        'weapon_change', 'ability_change', 'weapon_effect'
    ))
);
