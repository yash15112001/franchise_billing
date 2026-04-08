"""OpenAPI / Swagger metadata for UI and integration partners.

Rendered in Swagger UI (`/api/v1/docs`) and ReDoc (`/api/v1/redoc`).
"""

from __future__ import annotations

API_DESCRIPTION = """
## Franchise Billing API (v1)

HTTP API for franchise operations: users, franchises, catalog, customers, vehicles,
bookings, invoices, and payments.

### Base URL

All **versioned** routes live under the **`api_prefix`** (default **`/api/v1`**). Example:
`https://<host>/api/v1/auth/login`.

The **`GET /health`** endpoint is **not** under this prefix; it returns service liveness at the app root.

### Authentication

1. **Login (JSON)** — `POST /api/v1/auth/login` with body `{"username","password"}`.
   On success, `data` includes `access_token` and `user`.

2. **Authorize in Swagger** — Use **Authorize** and either:
   - Paste a bearer token, or
   - OAuth2 password flow uses `POST /api/v1/auth/token` (form: `username`, `password`).

3. **Calling protected routes** — Header:
   ```
   Authorization: Bearer <access_token>
   ```

4. **Franchise context (main admin)** — Some flows resolve franchise from the token; for
   **franchise-scoped** helpers that require an explicit franchise (e.g. certain `FranchiseScope`
   dependencies), the API may expect header **`X-Franchise-Id`**. Franchise staff/admin users
   are tied to one franchise in the token; do not send a conflicting `X-Franchise-Id`.

### Response shape (success)

```json
{
  "success": true,
  "message": "…",
  "data": { }
}
```

`data` may be an object, array, or scalar depending on the endpoint.

### Response shape (application errors)

Handled errors return JSON with:

```json
{
  "success": false,
  "message": "Human-readable message",
  "error_code": "SNAKE_CASE_CODE",
  "details": { }
}
```

The HTTP status matches the error (e.g. 400, 403, 404). Check **`error_code`** and **`details`**
for programmatic handling (e.g. `INVOICE_NOT_FOUND`, `OVERPAYMENT_EXCEEDS_LIMIT`).

### Validation errors (422)

Request body/query validation failures use a similar envelope with **`error_code`: `VALIDATION_ERROR`**
and **`details.errors`**: list of `{ loc, msg, type }`.

### Server errors (500)

Unexpected failures return **`success`: false**, **`error_code`: `INTERNAL_SERVER_ERROR`**.

### Typical HTTP status codes

| Code | Meaning |
|------|---------|
| 200 | OK — resource read or update succeeded (check `data`). |
| 201 | Created — resource created (check `data`). |
| 400 | Bad request — business rule violation (`error_code` in body). |
| 401 | Unauthorized — missing/invalid token. |
| 403 | Forbidden — wrong role/permission or franchise access. |
| 404 | Not found — id not found or not visible to actor. |
| 422 | Validation — body/query failed Pydantic validation (`VALIDATION_ERROR`). |
| 501 | Not implemented / not available in this API version (`NOT_AVAILABLE_IN_V1`, etc.). |
| 500 | Server error — unexpected (`INTERNAL_SERVER_ERROR`). |

Each route’s **docstring** in code names the request **schema** (when applicable) and notable **`error_code`** values; unknown domain errors still use the same AppError envelope.

### Conventions

- **Money**: Amounts are typically **strings** in JSON (e.g. `"123.45"`) for precision.
- **Timestamps**: ISO 8601 strings with timezone where applicable.
- **IDs**: Integer primary keys unless noted otherwise.
- **Permissions**: Endpoints require specific permissions; missing permission yields **403**
  with an appropriate message.

### Roles (summary)

- **Main admin** — Cross-franchise visibility where the contract allows it.
- **Franchise admin / staff** — Data limited to their **franchise** (enforced via invoice/booking
  franchise linkage, etc.).

### Not implemented in API v1

- **Reports** and **settlements** routers are not mounted in this build.
- Some routes return **501** with **`error_code`: `NOT_AVAILABLE_IN_V1`** (e.g. creating payments
  via `POST /payments` — use **`POST /invoices/{invoice_id}/payments`** instead; some invoice
  PATCH routes are intentionally unavailable in v1).

### Integration flow (typical)

1. `POST /auth/login` → store `access_token`.
2. Seed or load **franchises**, **customers**, **vehicles**, **services** as needed.
3. **Bookings** → **invoice** is created with the booking.
4. Record **payments** against invoices via **`POST /invoices/{invoice_id}/payments`**.
5. List or patch **payments** under **`/payments`** as per contracts.

For field-level rules and DB concepts, see internal docs: `docs/architecture/api_contracts.txt`,
`docs/architecture/schema_design.txt`.
""".strip()

# Order controls grouping in Swagger UI (tags must match router tags= exactly).
OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "auth",
        "description": (
            "Login, bootstrap (dev/setup), password change, and **`/auth/me`**. "
            "Use **`POST /auth/login`** for JSON login; Swagger **Authorize** may use **`POST /auth/token`** (form)."
        ),
    },
    {
        "name": "users",
        "description": "User accounts, roles, and permissions (per contract).",
    },
    {
        "name": "franchises",
        "description": "Franchise CRUD, timings, and franchise-scoped reads/updates.",
    },
    {
        "name": "services",
        "description": "Catalog services (offered work / SKUs) for bookings.",
    },
    {
        "name": "customers",
        "description": "Customer records linked to franchises.",
    },
    {
        "name": "vehicles",
        "description": "Vehicles per customer for bookings.",
    },
    {
        "name": "bookings",
        "description": (
            "Bookings and invoice creation. List/filter bookings; create booking; "
            "get/patch booking; replace booking line items (drives invoice totals)."
        ),
    },
    {
        "name": "booking-items",
        "description": (
            "Booking line items as a sub-resource. Prefer **`PUT /bookings/{id}/items`** "
            "for bulk line updates when building checkout flows."
        ),
    },
    {
        "name": "invoices",
        "description": (
            "Invoice listing and detail; **payments** are recorded with "
            "**`POST /invoices/{invoice_id}/payments`** (not `POST /payments`). "
            "Some GST/manual-status PATCH routes may return 501 in v1."
        ),
    },
    {
        "name": "payments",
        "description": (
            "List/get payments; **patch `reference_number` only**. "
            "**`POST /payments`** is disabled in v1 (use invoice payment endpoint)."
        ),
    },
]

API_VERSION = "1.0.0"
