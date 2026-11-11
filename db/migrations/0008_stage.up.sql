CREATE TABLE stage (
    id text PRIMARY KEY,
    column_count integer NOT NULL CHECK (column_count > 0),
    row_count integer NOT NULL CHECK (row_count > 0)
);

CREATE TABLE stage_terrain (
    stage_id text NOT NULL REFERENCES stage (id) ON DELETE CASCADE,
    cell_column integer NOT NULL CHECK (cell_column >= 0),
    cell_row integer NOT NULL CHECK (cell_row >= 0),
    terrain text NOT NULL
        CHECK (terrain IN ('space', 'atmospheric', 'ground', 'surface', 'underwater')),
    PRIMARY KEY (stage_id, cell_column, cell_row, terrain)
);

CREATE TABLE stage_deploy_cell (
    stage_id text NOT NULL REFERENCES stage (id) ON DELETE CASCADE,
    slot integer NOT NULL CHECK (slot >= 0),
    cell_column integer NOT NULL CHECK (cell_column >= 0),
    cell_row integer NOT NULL CHECK (cell_row >= 0),
    PRIMARY KEY (stage_id, slot),
    UNIQUE (stage_id, cell_column, cell_row)
);

CREATE TABLE stage_unit (
    stage_id text NOT NULL REFERENCES stage (id) ON DELETE CASCADE,
    sort integer NOT NULL CHECK (sort >= 0),
    anchor_column integer NOT NULL,
    anchor_row integer NOT NULL,
    width integer NOT NULL CHECK (width > 0),
    height integer NOT NULL CHECK (height > 0),
    faction text NOT NULL CHECK (faction IN ('ally', 'enemy')),
    controllable boolean NOT NULL,
    mech_role text NOT NULL
        CHECK (mech_role IN ('attack', 'endurance', 'support', 'no_role')),
    mech_name_mask bytea NOT NULL,
    hp integer NOT NULL,
    en integer NOT NULL,
    pilot_role text NOT NULL
        CHECK (pilot_role IN ('attack', 'endurance', 'support', 'no_role')),
    pilot_name_mask bytea NOT NULL,
    mp integer NOT NULL,
    mp_max integer NOT NULL,
    pilot_state text NOT NULL CHECK (pilot_state IN ('一般', '強勢', '超強勢', '超一擊')),
    PRIMARY KEY (stage_id, sort)
);
