CREATE TABLE supporter (
    stamp text NOT NULL,
    id bigint NOT NULL,
    name text NOT NULL,
    rarity integer NOT NULL,
    max_hp_addition integer NOT NULL,
    max_attack_addition integer NOT NULL,
    PRIMARY KEY (stamp, id)
);

CREATE TABLE supporter_limit_break (
    stamp text NOT NULL,
    supporter_id bigint NOT NULL,
    step integer NOT NULL,
    leader_skill jsonb NOT NULL,
    active_skill jsonb NOT NULL,
    PRIMARY KEY (stamp, supporter_id, step),
    FOREIGN KEY (stamp, supporter_id) REFERENCES supporter (stamp, id) ON DELETE CASCADE
);

CREATE TABLE supporter_growth (
    stamp text NOT NULL,
    level integer NOT NULL,
    limit_break integer NOT NULL,
    correction_rate integer NOT NULL,
    PRIMARY KEY (stamp, level, limit_break)
);
