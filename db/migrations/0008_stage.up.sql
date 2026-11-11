CREATE TABLE stage (
    id text NOT NULL,
    version text NOT NULL,
    column_count integer NOT NULL CHECK (column_count > 0),
    row_count integer NOT NULL CHECK (row_count > 0),
    PRIMARY KEY (id, version)
);

CREATE TABLE stage_terrain (
    stage_id text NOT NULL,
    stage_version text NOT NULL,
    cell_column integer NOT NULL CHECK (cell_column >= 0),
    cell_row integer NOT NULL CHECK (cell_row >= 0),
    terrain text NOT NULL
        CHECK (terrain IN ('space', 'atmospheric', 'ground', 'surface', 'underwater')),
    PRIMARY KEY (stage_id, stage_version, cell_column, cell_row, terrain),
    FOREIGN KEY (stage_id, stage_version) REFERENCES stage (id, version) ON DELETE CASCADE
);

CREATE TABLE stage_deploy_cell (
    stage_id text NOT NULL,
    stage_version text NOT NULL,
    slot integer NOT NULL CHECK (slot >= 0),
    cell_column integer NOT NULL CHECK (cell_column >= 0),
    cell_row integer NOT NULL CHECK (cell_row >= 0),
    PRIMARY KEY (stage_id, stage_version, slot),
    UNIQUE (stage_id, stage_version, cell_column, cell_row),
    FOREIGN KEY (stage_id, stage_version) REFERENCES stage (id, version) ON DELETE CASCADE
);

CREATE TABLE stage_unit (
    stage_id text NOT NULL,
    stage_version text NOT NULL,
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
    PRIMARY KEY (stage_id, stage_version, sort),
    FOREIGN KEY (stage_id, stage_version) REFERENCES stage (id, version) ON DELETE CASCADE
);
