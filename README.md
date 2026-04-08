# Franchise Billing Backend

Standalone FastAPI backend for the franchise billing platform.

## Structure

- `apps/` application entrypoints
- `domains/` business modules
- `foundation/` shared technical building blocks
- `contracts/` API contracts
- `docs/` architecture notes

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn apps.api.src.main:app --reload
```

Then update `.env` with your real database credentials. The API exposes:

- `GET /health`
- `POST /api/v1/auth/bootstrap-main-admin`
- `POST /api/v1/franchises`
- `POST /api/v1/bookings`
- `POST /api/v1/payments`
- `POST /api/v1/auth/login`

## Database

For local PostgreSQL, set:

```bash
DATABASE_URL=postgresql+psycopg://yash@127.0.0.1:5432/franchise_billing
```

<!-- SQLite fallback intentionally disabled. Use the local PostgreSQL instance instead. -->

If your PostgreSQL user has a password, use:

```bash
DATABASE_URL=postgresql+psycopg://postgres:your_password@127.0.0.1:5432/franchise_billing
```

## Table Creation

On app startup, the backend runs SQLAlchemy `create_all()` for the registered
models.

That means:

- the target database itself must already exist
- if the connection works and the database exists, running `uvicorn` will create
  the tables that do not exist yet
- the backend expects PostgreSQL as the local system of record
- it will not install or start the PostgreSQL server for you

## Current Billing Flow

- global services are managed once and reused across all franchises
- each franchise represents one standalone shop
- franchise-scoped operational endpoints use the authenticated user's franchise, or `X-Franchise-Id` for main admin flows
- booking creation creates the service receipt/registration first
- invoice generation happens when the first payment is recorded
- payments can be partial or full
