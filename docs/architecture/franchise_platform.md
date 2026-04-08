# Franchise Billing Platform

## Topology

The platform is designed as a cloud-first modular monolith with two execution
boundaries:

- `apps/api`: synchronous FastAPI application for operational workflows
- `apps/worker`: asynchronous workers for exports, notifications, PDFs, and backups

This keeps finance-sensitive flows transactional while still allowing
side-effect-heavy workloads to scale independently.

## Module Boundaries

Business capabilities live under `domains/`:

- `auth`: login and token issuance
- `rbac`: roles and permission checks
- `franchises`: franchise tenants and commission policies
- `customers`: customers and vehicles
- `catalog`: global service catalog and pricing
- `bookings`: booking receipt capture and operational service records
- `invoicing`: invoice numbering and invoice generation after payment starts
- `payments`: advance/full payments and balance allocation
- `settlements`: day-end closure and immutable settlement snapshots
- `reports`: daily operational and finance reports
- `notifications`: outbound messaging and reminder orchestration
- `audit`: immutable audit trail for sensitive actions

Cross-cutting technical concerns live under `foundation/`:

- `config`: environment-driven settings
- `database`: SQLAlchemy metadata, sessions, and bootstrap helpers
- `security`: password hashing and JWT helpers
- `web`: shared API dependencies

## Layering Rules

Every domain follows four layers:

- `domain/`: pure business types, enums, and policy rules
- `application/`: use cases and orchestration logic
- `infrastructure/`: ORM models and external adapters
- `interfaces/`: HTTP routers and worker consumers

Allowed dependency direction:

1. `interfaces` -> `application`
2. `application` -> `domain`
3. `application` -> `infrastructure` through explicit persistence usage
4. `foundation` never imports domain business logic

## Multi-Tenancy Model

The platform uses logical multi-tenancy with row-level scoping:

- every business record is scoped by `franchise_id`
- each franchise represents one standalone shop in the product domain
- main admin users can operate across franchises
- franchise admins and staff are restricted to their assigned franchise
- `X-Franchise-Id` is only needed when a main admin must select a franchise-scoped workflow

## Finance Safety Rules

- bookings are created before invoices
- invoices are append-only after finalization
- payment allocation is modeled explicitly instead of mutating totals blindly
- commission changes are history-based through policy records
- settlements are immutable snapshots
- destructive financial deletes are not supported in the application workflow

## Recommended Growth Path

Phase 1 delivers the cloud backend and the core billing loop.

Phase 2 adds async exports, notifications, and operator tooling.

Phase 3 can introduce offline-first client sync or selective domain extraction
only if scale, latency, or ownership boundaries justify it.

## Runtime Notes

Local development and production both expect `DATABASE_URL` to point to
PostgreSQL as the system of record.
