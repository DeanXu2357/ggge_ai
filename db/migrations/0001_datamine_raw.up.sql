CREATE TABLE datamine_raw (
    stamp text NOT NULL,
    source_table text NOT NULL,
    row_key text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (stamp, source_table, row_key)
);
