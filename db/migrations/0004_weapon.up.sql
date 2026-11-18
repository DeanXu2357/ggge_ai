-- No foreign key to 'unit': the weapon table names owners that the unit
-- table does not hold (docs/reference/datamine-source.md).
CREATE TABLE weapon (
    stamp text NOT NULL,
    id bigint NOT NULL,
    unit_id bigint NOT NULL,
    name text NOT NULL,
    type integer NOT NULL,
    work_type integer NOT NULL,
    attack_attr integer NOT NULL,
    weapon_attr integer NOT NULL,
    power integer NOT NULL,
    en integer NOT NULL,
    hit_rate integer NOT NULL,
    critical_rate integer NOT NULL,
    range_min integer NOT NULL,
    range_max integer NOT NULL,
    ammo integer NOT NULL,
    is_ssp boolean NOT NULL,
    PRIMARY KEY (stamp, id)
);

CREATE INDEX weapon_owner ON weapon (stamp, unit_id);

CREATE TABLE weapon_growth (
    stamp text NOT NULL,
    weapon_id bigint NOT NULL,
    level integer NOT NULL,
    power_rate integer NOT NULL,
    en_rate integer NOT NULL,
    hit_rate_rate integer NOT NULL,
    crit_rate_rate integer NOT NULL,
    PRIMARY KEY (stamp, weapon_id, level),
    FOREIGN KEY (stamp, weapon_id) REFERENCES weapon (stamp, id) ON DELETE CASCADE
);

CREATE TABLE weapon_trait (
    stamp text NOT NULL,
    weapon_id bigint NOT NULL,
    sort integer NOT NULL,
    level integer NOT NULL,
    trait_id bigint NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (stamp, weapon_id, sort),
    FOREIGN KEY (stamp, weapon_id) REFERENCES weapon (stamp, id) ON DELETE CASCADE
);
