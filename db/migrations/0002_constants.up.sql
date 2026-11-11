CREATE TABLE level_curve (
    level integer PRIMARY KEY,
    rate integer NOT NULL
);

CREATE TABLE limit_break_rate (
    step integer PRIMARY KEY,
    rate_percent integer NOT NULL
);

CREATE TABLE rarity_level_cap (
    rarity integer PRIMARY KEY,
    cap integer NOT NULL
);
