CREATE TABLE holding (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    stamp text NOT NULL,
    unit_id bigint NOT NULL,
    level integer NOT NULL,
    limit_break integer NOT NULL DEFAULT 0,
    mech_sp boolean NOT NULL DEFAULT false,
    mech_ssp boolean NOT NULL DEFAULT false,
    weapon_level integer NOT NULL DEFAULT 5,
    pilot_id bigint,
    pilot_level integer,
    supporter_id bigint,
    supporter_level integer,
    supporter_limit_break integer,
    FOREIGN KEY (stamp, unit_id) REFERENCES unit (stamp, id),
    FOREIGN KEY (stamp, pilot_id) REFERENCES pilot (stamp, id),
    FOREIGN KEY (stamp, supporter_id) REFERENCES supporter (stamp, id)
);
