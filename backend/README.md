# Campus League backend

Django + Django REST Framework on PostgreSQL. The API contract is in
[`docs/API_CONTRACT.md`](../docs/API_CONTRACT.md).

## Requirements

- Python 3.12 or newer (developed on 3.14)
- Docker with Compose (Docker Desktop or Colima). The database runs in a
  container; nothing else needs Docker.

## First-time setup

Run everything from the `backend/` folder.

```bash
# 1. Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Local settings (never commit .env)
cp .env.example .env
```

Open `.env` and replace both `change-me` values:

- `DJANGO_SECRET_KEY`: generate one with
  `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`
- `POSTGRES_PASSWORD`: any password; it only protects your local database.

```bash
# 3. Database (PostgreSQL 17 on localhost:5433)
docker compose up -d --wait

# 4. Tables
python manage.py migrate
```

## Everyday commands

```bash
source .venv/bin/activate
docker compose up -d --wait        # start the database
python manage.py runserver         # API at http://127.0.0.1:8000/api/
python manage.py test              # run all tests (uses a throwaway database)
docker compose stop                # stop the database, keep its data
```

After pulling new code, run `pip install -r requirements.txt` and
`python manage.py migrate` again.

## Admin and roles

Until the roles endpoint exists, roles are assigned in the Django admin.

```bash
python manage.py createsuperuser   # asks for email, name, college ID, password
```

Then open http://127.0.0.1:8000/admin/ and add a **Role assignment** for a
user. A role is current while today is between its term start and term end.

## Troubleshooting

- **`KeyError: 'DJANGO_SECRET_KEY'`**: `backend/.env` is missing or incomplete.
- **`connection refused` on port 5433**: the database is not running; run
  `docker compose up -d --wait`.
- **`password authentication failed`**: `POSTGRES_PASSWORD` changed after the
  database was first created. `docker compose down -v` deletes the local
  database (all local data is lost); then start it again and re-run `migrate`.
- **Port 5433 already in use**: change `POSTGRES_PORT` in `.env`.
