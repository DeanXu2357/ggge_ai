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
