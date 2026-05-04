# AWS RDS + EC2 Deployment Runbook

This document captures the deployment flow used to run the FastAPI backend on
an EC2 instance and connect it to a PostgreSQL database hosted on Amazon RDS.

The final working shape was:

- `RDS PostgreSQL` for the production database
- `EC2 Ubuntu` for the FastAPI server
- `systemd` to keep `uvicorn` running
- `nginx` on port `80` as the public reverse proxy

## 1. Create the Database in AWS RDS

From the AWS Console:

1. Go to `RDS` -> `Databases` -> `Create database`
2. Choose:
   - creation method: `Standard create`
   - engine: `PostgreSQL`
   - template: `Free tier` or `Dev/Test`
3. Set:
   - DB instance identifier: `franchise-billing-test-db`
   - master username: `franchiseadmin`
   - initial database name: `franchise_billing`
4. In connectivity:
   - use the target VPC
   - for temporary local CLI access, set `Publicly accessible` to `Yes`
5. In the RDS security group, allow:
   - `PostgreSQL` / `5432` from your laptop public IP, for example `103.251.59.57/32`

If the `franchise_billing` database was not created during setup, connect to the
default `postgres` database and create it manually:

```bash
psql -h franchise-billing-test-db.cpe0ygww0gdd.ap-south-1.rds.amazonaws.com -p 5432 -U franchiseadmin -d postgres
```

Then run inside `psql`:

```sql
CREATE DATABASE franchise_billing;
```

## 2. Verify Local CLI Access to RDS

Once the DB instance is available and the security group allows your IP, connect
from local:

```bash
psql -h franchise-billing-test-db.cpe0ygww0gdd.ap-south-1.rds.amazonaws.com -p 5432 -U franchiseadmin -d franchise_billing
```

If that works, the database is reachable and the application can use this
connection string:

```bash
DATABASE_URL=postgresql+psycopg://franchiseadmin:<password>@franchise-billing-test-db.cpe0ygww0gdd.ap-south-1.rds.amazonaws.com:5432/franchise_billing
```

## 3. Launch the EC2 Instance

From the AWS Console:

1. Go to `EC2` -> `Instances` -> `Launch instance`
2. Choose:
   - name: `franchise-billing-test-api`
   - AMI: `Ubuntu Server 24.04 LTS`
   - instance type: `t3.micro`
   - key pair: `franchise-billing-ec2-server-access-key`
3. Use the same VPC as the RDS instance
4. Enable a public IPv4 address
5. Create an EC2 security group with inbound rules:
   - `SSH` from `My IP`
   - `HTTP` from `0.0.0.0/0`
   - `HTTPS` from `0.0.0.0/0`

Important:

- `SSH` must be limited to your IP, not `0.0.0.0/0`
- these rules belong to the EC2 security group, not the RDS security group

## 4. Allow the New EC2 Instance to Reach RDS

After the EC2 instance is created, update the RDS security group so the backend
can reach PostgreSQL:

- add inbound rule: `PostgreSQL` / `5432`
- source: the EC2 instance security group

At this point, the RDS security group can contain both:

- your laptop IP, for direct `psql` access
- the EC2 security group, for app-to-database access

## 5. SSH Into the Ubuntu Instance

On your laptop:

```bash
chmod 400 ~/Downloads/franchise-billing-ec2-server-access-key.pem
ssh -i ~/Downloads/franchise-billing-ec2-server-access-key.pem ubuntu@<ec2-public-ip>
```

Note:

- the SSH username is `ubuntu` for Ubuntu AMIs
- a previous failed attempt happened because an Amazon Linux AMI was launched by mistake, which would have required `ec2-user`

## 6. Install System Packages on EC2

On the Ubuntu instance:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git postgresql-client
```

The generic package names were required because `python3.12-venv` was not
available by that exact package name on the chosen image.

## 7. Clone the Repository and Set Up the App Environment

Clone the repository:

```bash
git clone https://github.com/yash15112001/franchise_billing.git
cd franchise_billing
```

Create the virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `.env` in the repo root and set the real production values:

```env
APP_ENV=production
API_PREFIX=/api/v1
DATABASE_URL=postgresql+psycopg://franchiseadmin:<password>@franchise-billing-test-db.cpe0ygww0gdd.ap-south-1.rds.amazonaws.com:5432/franchise_billing
BOOTSTRAP_ADMIN_SECRET=<long-random-secret>
JWT_SECRET_KEY=<long-random-secret>
```

## 8. Verify EC2 Can Reach the Database

From the EC2 instance:

```bash
psql -h franchise-billing-test-db.cpe0ygww0gdd.ap-south-1.rds.amazonaws.com -p 5432 -U franchiseadmin -d franchise_billing
```

If that works, EC2-to-RDS networking is correct.

## 9. Verify the App Manually Before Backgrounding It

From the repo root on EC2:

```bash
source .venv/bin/activate
uvicorn apps.api.src.main:app --host 127.0.0.1 --port 8000
```

Then test on the EC2 machine:

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","app":"Franchise Billing Platform"}
```

This confirmed the FastAPI app was healthy before introducing `systemd` and
`nginx`.

## 10. Run the App as a systemd Service

Create the service file:

```bash
sudo nano /etc/systemd/system/franchise-billing.service
```

Paste:

```ini
[Unit]
Description=Franchise Billing FastAPI
After=network.target

[Service]
User=ubuntu
Group=ubuntu
WorkingDirectory=/home/ubuntu/franchise_billing
Environment="PATH=/home/ubuntu/franchise_billing/.venv/bin"
ExecStart=/home/ubuntu/franchise_billing/.venv/bin/uvicorn apps.api.src.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Then enable and start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable franchise-billing
sudo systemctl start franchise-billing
sudo systemctl status franchise-billing
```

If troubleshooting is needed:

```bash
sudo journalctl -u franchise-billing -n 50 --no-pager
```

## 11. Put nginx in Front of the App

Create the nginx site config:

```bash
sudo nano /etc/nginx/sites-available/franchise-billing
```

Paste:

```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/franchise-billing /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl status nginx
```

## 12. Fix the Default nginx Site Conflict

At first, `curl http://127.0.0.1:8000/health` worked, but
`curl http://127.0.0.1/health` returned nginx `404 Not Found`.

The issue was that the default nginx site was still enabled. The fix was:

```bash
ls -l /etc/nginx/sites-enabled
sudo rm /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/franchise-billing /etc/nginx/sites-enabled/franchise-billing
sudo nginx -t
sudo systemctl reload nginx
```

Then:

```bash
curl http://127.0.0.1/health
```

returned the expected health response.

## 13. Verify Public Access

Once nginx was correctly proxying to the app, the API became reachable from the
internet through the EC2 public IP:

```bash
curl http://<ec2-public-ip>/health
```

This confirmed:

- EC2 security group allowed inbound HTTP traffic
- nginx was listening on port `80`
- nginx was proxying correctly to `uvicorn`
- `uvicorn` was serving the FastAPI app on `127.0.0.1:8000`

## 14. Commands Actually Used on EC2

These are the main commands that were part of the successful flow, cleaned up to
remove retries and failed package guesses:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx git postgresql-client
git clone https://github.com/yash15112001/franchise_billing.git
cd franchise_billing
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
touch .env
nano .env
psql -h franchise-billing-test-db.cpe0ygww0gdd.ap-south-1.rds.amazonaws.com -p 5432 -U franchiseadmin -d franchise_billing
uvicorn apps.api.src.main:app --host 127.0.0.1 --port 8000
sudo nano /etc/systemd/system/franchise-billing.service
sudo systemctl daemon-reload
sudo systemctl enable franchise-billing
sudo systemctl start franchise-billing
sudo nano /etc/nginx/sites-available/franchise-billing
sudo ln -s /etc/nginx/sites-available/franchise-billing /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo rm /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/franchise-billing /etc/nginx/sites-enabled/franchise-billing
sudo nginx -t
sudo systemctl reload nginx
curl http://127.0.0.1:8000/health
curl http://127.0.0.1/health
```

## 15. Recommended Cleanup After Initial Deployment

After the deployment is stable, tighten access:

- remove the temporary laptop IP rule from the RDS security group if direct local
  DB access is no longer needed
- keep only the EC2 security group allowed to reach RDS on `5432`
- consider switching RDS back to `Publicly accessible = No`
- add HTTPS with a real domain later instead of using only public HTTP
