# 32 · One configuration file (`chore/single-env`)

## Before: three `.env` files
| File | Read by |
|---|---|
| `.env` (root) | Docker Compose, to fill `${POSTGRES_*}` in `docker-compose.yaml` |
| `backend/.env` | the FastAPI app |
| `frontend/.env` | Vite (`VITE_API_BASE_URL`) |

The real problem was **duplication**: the Postgres user/password lived in the root `.env` *and* inside the two database URLs in `backend/.env`. Change one, forget the other, and the backend can't connect.

## After: `backend/.env` is the single source of truth
- `docker-compose.yaml` uses `env_file: ./backend/.env`. The Postgres image reads `POSTGRES_USER/PASSWORD/DB` from it.
- `config.py` **builds** `DATABASE_URL_ASYNC/SYNC` from `POSTGRES_*` (+ `POSTGRES_HOST`/`PORT`, defaulting to `localhost:5433`). Full URLs can still be set to override, e.g. for a hosted database.
- URLs are built with SQLAlchemy's `URL.create`, which **URL-encodes the password**: `p@ss/w:rd` → `p%40ss%2Fw%3Ard`. With an f-string, `@` or `/` in a password would corrupt the URL.
- `frontend/.env` is optional: the code defaults to `http://127.0.0.1:8000`. Anything in a Vite `.env` is **baked into the JavaScript the browser downloads**, so it must never hold secrets.
- The root `.env.example` was removed.

## Trade-off chosen: `env_file:` (convenience) vs `--env-file` (least privilege)
`env_file:` gives the Postgres container *every* variable in `backend/.env`, API keys included (visible via `docker inspect`). The stricter alternative, interpolating only `POSTGRES_*` with `docker compose --env-file backend/.env up -d`, needs a flag that's easy to forget. For local development the convenience wins, because the same person already has the file. For a shared or production deployment, use a separate secrets mechanism.

## Migration of the local files
The values were checked to match (user, password, database) *without printing them*. `POSTGRES_*` moved into `backend/.env`, the duplicate URLs were removed, and the old files were backed up and deleted.

## Verified
URLs build correctly; `alembic current` at head; containers recreated with **data intact** (144 users before and after); 36 backend tests pass; live register → create conversation → list works.
