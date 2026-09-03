# The game data store

> Type: how-to—must match the current workflow

The game data store is a PostgreSQL database. It holds the crawled
datamine (`docs/reference/datamine-source.md`) in a raw form and in
a normalized form, and the constant tables of the growth model. The
loader reads the store and writes the payload that the engine loads
before a run. The engine never connects to the store.

## Start the database

The file `compose.yaml` at the repository root defines one service,
`postgres`, from the image `postgres:16`. The database, the user
and the password are all `ggge`. The port is 5432. The data lives
in the named volume `ggge_ai_postgres-data`, so the rows survive a
restart of the container.

    docker compose up -d
    docker compose exec postgres pg_isready -U ggge

Stop the container with `docker compose down`. Add `-v` to remove
the volume too.

The connection string is the environment variable
`GGGE_DATABASE_URL`. Its default is
`postgresql://ggge:ggge@localhost:5432/ggge`. Set the variable when
the database is somewhere else.

## Apply the migrations

The schema lives in `db/migrations/` as plain SQL, one `.up.sql`
and one `.down.sql` for each step. The tool is the golang-migrate
CLI. Install it one time:

    go install -tags 'postgres' github.com/golang-migrate/migrate/v4/cmd/migrate@latest

The binary lands in `$(go env GOPATH)/bin`. Then apply every step:

    migrate -path db/migrations \
        -database "postgresql://ggge:ggge@localhost:5432/ggge?sslmode=disable" up

The query `sslmode=disable` is for the CLI alone. The Python side
reads `GGGE_DATABASE_URL` without it.

`migrate ... version` prints the current step. `migrate ... down 1`
reverts one step. `migrate ... down -all` empties the schema.

## Add a migration

1. Take the next number, four digits, and a short name:
   `db/migrations/0008_<name>.up.sql` and `0008_<name>.down.sql`.
2. Write the `up` file so that the `down` file reverts it fully.
3. Apply `up`, then `down 1`, then `up` again against a local
   database before you commit.

Every normalized table carries the column `stamp`, the data version
stamp of the datamine. A crawl at a new stamp adds rows beside the
old ones; it changes no existing row.

## Crawl and ingest

Crawl the datamine one time for each data version:

    uv run python scripts/crawl_datamine.py

The crawl writes the dump `data/datamine/<stamp>/`. The directory
holds one JSON file for each source and the file `manifest.json`.
The stamp is the data version of the source.

Ingest the newest dump:

    uv run python scripts/ingest_datamine.py

Name a directory to ingest a different dump:

    uv run python scripts/ingest_datamine.py data/datamine/202609010310

The ingest writes three groups of rows:

1. the payload of each source row, in `datamine_raw`;
2. the normalized rows of the unit, the weapon, the pilot and the
   support crew tables;
3. the constant tables of the growth model.

The ingest deletes the rows of the stamp first, then it inserts the
new rows. A second ingest of the same dump gives the same rows. The
rows of the other stamps do not change.

Remove one stamp:

    uv run python -c \
        "from ggge_ai.gamedata.store import Store; Store().delete_stamp('202609010310')"

The constant tables carry no stamp. A delete of a stamp keeps them.
These are the three tables of `growth.py`: `level_curve`,
`limit_break_rate` and `rarity_level_cap`. The support crew growth
table `supporter_growth` comes from the dump, so it carries the stamp
like the rest. A delete of a stamp removes its rows.

## Load a holding

The loader turns one holding into the payload that the engine loads.
Name the mech, the level and the pilot:

    uv run python scripts/load_holding.py \
        --stamp 202609010310 \
        --unit 1001003000 --level 100 --limit-break 3 \
        --mech-sp --mech-ssp --weapon-level 5 \
        --pilot 1001000100 --pilot-level 100 \
        --supporter 1001000150 --supporter-level 100 \
        --supporter-limit-break 3

The flags:

| Flag | Meaning |
|---|---|
| `--stamp` | the data version stamp to read |
| `--unit`, `--level` | the mech and its level |
| `--limit-break` | the star count, 0 to 3, default 0 |
| `--mech-sp`, `--mech-ssp` | the two upgrades; `--mech-ssp` needs `--mech-sp` |
| `--weapon-level` | 1 to 5, default 5 |
| `--pilot`, `--pilot-level` | the pilot and its level |
| `--supporter` | the support crew, with the two flags that it needs: `--supporter-level` and `--supporter-limit-break`. Give the three flags together, or give none of them |
| `--from-dump` | read a datamine dump instead of the database |
| `--database-url` | override `GGGE_DATABASE_URL` |

`--from-dump DIR` reads the five table files of a dump directly:

    uv run python scripts/load_holding.py --stamp 202609010310 \
        --from-dump tests/fixtures/datamine \
        --unit 1001000100 --level 50 --weapon-level 3 \
        --pilot 1001000200 --pilot-level 30

The script prints one JSON object with three keys:

- `mech`: the wire form of `battle.Mech`;
- `pilot`: the wire form of `battle.Pilot`;
- `crew`: `{"hp": n, "attack": n}`, or `null` with no support crew.
  The wire has no field for the crew bonus, so the loader writes it
  beside the payload (issue #72).

The `mech.weapons` list holds the direct weapons alone. The datamine
type 2 (Ex weapon) and type 3 (map weapon) stay in the store; this
issue emits neither, and `map_weapons` is always empty.

The golden payloads in `tests/fixtures/gamedata/` come from this
script against `tests/fixtures/datamine`.

## Run the store tests

The tests in `tests/test_gamedata_store.py` need a database. Pytest
skips them when the environment variable `GGGE_DATABASE_URL` is not
set. Set the variable to run them:

    GGGE_DATABASE_URL=postgresql://ggge:ggge@localhost:5432/ggge \
        uv run pytest -q tests/test_gamedata_store.py

The tests write the stamps `test-202609010310` and
`test-holding-202609010310` and delete them at the end. They touch no
other stamp.
