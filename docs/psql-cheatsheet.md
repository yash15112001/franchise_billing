# PostgreSQL CLI Cheatsheet

This project uses the local PostgreSQL database from `.env`:

```bash
DATABASE_URL=postgresql+psycopg://yash@127.0.0.1:5432/franchise_billing
```

That means the main database values are:

- user: `yash`
- host: `127.0.0.1`
- port: `5432`
- database: `franchise_billing`

## Connect

Connect directly to the app database:

```bash
psql -h 127.0.0.1 -p 5432 -U yash -d franchise_billing
```

Connect to the default admin database:

```bash
psql -h 127.0.0.1 -p 5432 -U yash -d postgres
```

If your local PostgreSQL user is already your macOS user and trust auth is configured, this shorter form also works:

```bash
psql -d franchise_billing
```

## Useful `psql` Meta Commands

Run these after entering `psql`:

```sql
\l
\c franchise_billing
\dt
\d bookings
\d invoices
\d payments
\d franchises
\dn
\du
\q
```

What they do:

- `\l` lists databases
- `\c franchise_billing` connects to the database
- `\dt` lists tables
- `\d table_name` describes a table
- `\dn` lists schemas
- `\du` lists database roles/users
- `\q` exits `psql`

## Create / Drop Database

Drop the database safely:

```bash
psql -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'franchise_billing' AND pid <> pg_backend_pid();"
psql -d postgres -c "DROP DATABASE IF EXISTS franchise_billing;"
```

Create it again:

```bash
psql -d postgres -c "CREATE DATABASE franchise_billing;"
```

After creating the empty database, start the app so SQLAlchemy creates the tables:

```bash
source .venv/bin/activate
uvicorn apps.api.src.main:app --reload
```

## See Tables and Structure

List all tables:

```bash
psql -d franchise_billing -c "\dt"
```

Describe a specific table:

```bash
psql -d franchise_billing -c "\d franchises"
psql -d franchise_billing -c "\d bookings"
psql -d franchise_billing -c "\d invoices"
psql -d franchise_billing -c "\d payments"
```

List only public tables with SQL:

```bash
psql -d franchise_billing -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
```

## Inspect Data

See all franchises:

```bash
psql -d franchise_billing -c "SELECT * FROM franchises;"
```

See all users:

```bash
psql -d franchise_billing -c "SELECT id, username, franchise_id, is_active, created_at FROM users ORDER BY id;"
```

See roles:

```bash
psql -d franchise_billing -c "SELECT id, name, is_system FROM roles ORDER BY id;"
```

See customers:

```bash
psql -d franchise_billing -c "SELECT id, full_name, mobile_number, franchise_id FROM customers ORDER BY id;"
```

See bookings:

```bash
psql -d franchise_billing -c "SELECT id, franchise_id, customer_id, vehicle_id, status, gst_enabled, total_amount, created_at FROM bookings ORDER BY id;"
```

See booking line items:

```bash
psql -d franchise_billing -c "SELECT id, booking_id, service_id, service_name, quantity, unit_price, line_total FROM booking_line_items ORDER BY id;"
```

See invoices:

```bash
psql -d franchise_billing -c "SELECT id, franchise_id, booking_id, invoice_number, invoice_type, total_amount, amount_paid, pending_amount, status FROM invoices ORDER BY id;"
```

See payments:

```bash
psql -d franchise_billing -c "SELECT id, franchise_id, invoice_id, amount, payment_method, payment_kind, created_at FROM payments ORDER BY id;"
```

See settlements:

```bash
psql -d franchise_billing -c "SELECT id, franchise_id, business_date, total_income, pending_income, status FROM daily_settlements ORDER BY id;"
```

## Search / Filter Examples

Find one franchise by code:

```bash
psql -d franchise_billing -c "SELECT * FROM franchises WHERE code = 'F001';"
```

Find one user by username:

```bash
psql -d franchise_billing -c "SELECT * FROM users WHERE username = 'admin';"
```

Find bookings for one franchise:

```bash
psql -d franchise_billing -c "SELECT id, status, total_amount, created_at FROM bookings WHERE franchise_id = 1 ORDER BY created_at DESC;"
```

Find unpaid or partially paid invoices:

```bash
psql -d franchise_billing -c "SELECT id, invoice_number, total_amount, amount_paid, pending_amount, status FROM invoices WHERE pending_amount > 0 ORDER BY id;"
```

Find payments for one invoice:

```bash
psql -d franchise_billing -c "SELECT * FROM payments WHERE invoice_id = 1 ORDER BY created_at;"
```

## Insert / Delete During Local Development

Insert one franchise:

```bash
psql -d franchise_billing -c "INSERT INTO franchises (name, code, city, state) VALUES ('Demo Franchise', 'DF001', 'Pune', 'MH');"
```

Delete all rows from a table:

```bash
psql -d franchise_billing -c "TRUNCATE TABLE payments RESTART IDENTITY CASCADE;"
```

Delete all app data while keeping tables:

```bash
psql -d franchise_billing -c \"TRUNCATE TABLE audit_logs, booking_line_items, bookings, customers, daily_settlements, franchise_commission_policies, franchises, global_services, invoice_items, invoice_sequences, invoices, payment_allocations, payments, permissions, role_permissions, roles, user_roles, users, vehicles RESTART IDENTITY CASCADE;\"
```

## Run Raw Queries Interactively

Start `psql`:

```bash
psql -d franchise_billing
```

Then run SQL like:

```sql
SELECT * FROM franchises;

SELECT id, username, franchise_id
FROM users
ORDER BY id;

SELECT id, invoice_number, total_amount, pending_amount
FROM invoices
ORDER BY id DESC;
```

## Export Query Output

Save query output to CSV:

```bash
psql -d franchise_billing -c "\copy (SELECT * FROM invoices ORDER BY id) TO 'invoices.csv' CSV HEADER"
```

## Handy One-Liners

Count rows in core tables:

```bash
psql -d franchise_billing -c "SELECT 'franchises' AS table_name, COUNT(*) FROM franchises UNION ALL SELECT 'users', COUNT(*) FROM users UNION ALL SELECT 'customers', COUNT(*) FROM customers UNION ALL SELECT 'bookings', COUNT(*) FROM bookings UNION ALL SELECT 'invoices', COUNT(*) FROM invoices UNION ALL SELECT 'payments', COUNT(*) FROM payments;"
```

See the latest 10 audit logs:

```bash
psql -d franchise_billing -c "SELECT id, action, entity_name, entity_id, actor_user_id, franchise_id, created_at FROM audit_logs ORDER BY id DESC LIMIT 10;"
```

## Recommended Everyday Flow

```bash
# 1. Connect
psql -d franchise_billing

# 2. Inspect tables
\dt

# 3. Describe a table
\d bookings

# 4. Run some SQL
SELECT * FROM franchises;

# 5. Exit
\q
```
