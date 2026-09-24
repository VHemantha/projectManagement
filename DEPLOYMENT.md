# Deploying TrackFlow to AWS (free-tier setup)

This guide takes TrackFlow from this repo to a live HTTPS URL on AWS using only
free-tier-eligible services, with no ECS, Fargate, App Runner or Copilot.

```
                         ┌──────────────────────── CloudFront (HTTPS, free forever tier) ────────────────────────┐
 Browser ── HTTPS ──────►│  /*          → S3 bucket (React build, private, via Origin Access Control)            │
                         │  /api/* /ws/* /admin/* /media/* /static/*  → EC2 (HTTP :80 + secret header)           │
                         └───────────────────────────────────────────────────────────────────────────────────────┘
                                                                  │
                         EC2 t2/t3.micro (Ubuntu 24.04)           ▼
                         nginx :80 ──► gunicorn + uvicorn workers (Django ASGI: REST + chat WebSockets) :8000
                                        │            │
                                        ▼            ▼
                                   Redis (local)   Postgres ── on the same box (DatabaseMode=local)
                                                             └─ or RDS db.t3.micro (DatabaseMode=rds)
```

Because CloudFront serves the frontend and the API from **one domain**, the React app's
relative `/api`, `/ws` and `/media` calls work unchanged. You don't need to configure CORS or
change any frontend code, and you get HTTPS on `https://dxxxx.cloudfront.net` without buying a
domain.

## What's in the repo

| Path | Purpose |
|---|---|
| `deploy/cloudformation/trackflow.yaml` | Creates the VPC, security groups, EC2 + Elastic IP, optional RDS, S3 bucket and CloudFront |
| `deploy/ec2/server_deploy.sh` | Runs **on the server** each deploy: installs dependencies, migrates, runs collectstatic and `bootstrap`, installs nginx/systemd config, switches release, health-checks |
| `deploy/ec2/nginx.conf`, `trackflow.service` | nginx site and the gunicorn systemd unit |
| `deploy/ec2/backup_db.sh` | Nightly `pg_dump` + media archive (installed as a cron job) |
| `deploy/ec2/trackflow-manage.sh` | `sudo trackflow-manage <cmd>` runs `manage.py` on the server |
| `deploy/scripts/deploy_backend.sh` | Run from your PC or CI: packages the committed backend, uploads it and runs `server_deploy.sh` |
| `deploy/scripts/deploy_frontend.sh` | Run from your PC or CI: builds React, syncs to S3, invalidates CloudFront |
| `.github/workflows/deploy.yml` | CI tests on every push; optional auto-deploy on `main` |
| `backend/apps/orgs/management/commands/bootstrap.py` | Creates the system issue types a fresh DB needs (runs every deploy) |

---

## 0. Before you start: costs

- **Which free tier do you have?** AWS accounts created **before 15 July 2025** get the
  "legacy" free tier: 12 months of 750 h/month EC2 micro, 750 h RDS micro, 30 GB EBS and
  5 GB S3. Accounts created **on or after 15 July 2025** get the newer credit-based free
  plan instead: sign-up credits (up to $200) that last up to 6 months. Check
  **Billing → Free Tier** in the console to see which one you have.
- **Always free** (any account age): CloudFront (1 TB transfer and 10 M requests/month) and
  CloudFront Functions (2 M invocations/month).
- **Public IPv4 addresses** (including the Elastic IP) cost about $0.005/hour, roughly $3.60/month.
  The legacy free tier covers 750 h/month of this for 12 months.
- **After the free period**, expect roughly: EC2 t3.micro ~$7–8/mo, 20 GB EBS ~$1.60/mo,
  IPv4 ~$3.60/mo, RDS micro ~$13–15/mo + storage. Choose `DatabaseMode=local`
  to avoid the RDS cost entirely.
- **Set a budget alarm first:** Billing → Budgets → Create budget → "Zero spend budget". It
  emails you the moment anything starts costing money.

## 1. Install tools (Windows)

Run every command in this guide in **Git Bash** (installed with Git for Windows), from the
repo root, unless it says otherwise.

1. **AWS CLI v2**: https://awscli.amazonaws.com/AWSCLIV2.msi. Then restart Git Bash and run
   `aws --version`.
2. **Node.js 22 LTS**: required by Vite 8 for the frontend build.
3. Git Bash rewrites arguments that start with `/` into Windows paths, which breaks AWS CLI
   calls such as `--name /aws/service/...`. Turn that off for your session:

   ```bash
   export MSYS_NO_PATHCONV=1
   ```

   (The deploy scripts already do this themselves.)

## 2. Give the CLI credentials

1. AWS console → **IAM → Users → Create user** (e.g. `trackflow-admin`) → attach the
   `AdministratorAccess` policy. It's only for creating the stack; step 11 sets up a
   narrower user for CI.
2. Open the user → **Security credentials → Create access key** → "Command Line Interface".
3. Configure the CLI with a region close to your users (e.g. `ap-south-1`, `eu-west-1`,
   `us-east-1`):

   ```bash
   aws configure
   # AWS Access Key ID:     AKIA...
   # AWS Secret Access Key: ...
   # Default region name:   ap-south-1
   # Default output format: json
   aws sts get-caller-identity     # sanity check: prints your account id
   ```

## 3. Create an SSH key pair

```bash
mkdir -p ~/.ssh
aws ec2 create-key-pair --key-name trackflow-key --key-type ed25519 \
  --query KeyMaterial --output text > ~/.ssh/trackflow-key.pem
chmod 600 ~/.ssh/trackflow-key.pem
```

Keep this file safe. It's the only way to SSH into the server (besides Session Manager in
the AWS console).

## 4. Collect the stack parameters

```bash
# Latest Ubuntu 24.04 AMI for your region
AMI_ID=$(aws ssm get-parameter \
  --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
  --query Parameter.Value --output text)

# Your public IP (allowed to SSH in)
MY_IP=$(curl -s https://checkip.amazonaws.com)

# AWS-managed list of CloudFront's IP ranges, so only CloudFront can reach port 80
CF_PREFIX_LIST=$(aws ec2 describe-managed-prefix-lists \
  --filters Name=prefix-list-name,Values=com.amazonaws.global.cloudfront.origin-facing \
  --query "PrefixLists[0].PrefixListId" --output text)

# Two random secrets (letters/digits only)
DB_PASSWORD=$(python -c "import secrets; print(secrets.token_hex(16))")
ORIGIN_SECRET=$(python -c "import secrets; print(secrets.token_hex(24))")

echo "AMI=$AMI_ID IP=$MY_IP PL=$CF_PREFIX_LIST"
echo "DB_PASSWORD=$DB_PASSWORD"
echo "ORIGIN_SECRET=$ORIGIN_SECRET"
```

**Save `DB_PASSWORD` and `ORIGIN_SECRET` in a password manager.** They're also written to
`/srv/trackflow/shared/.env` on the server.

**Choose a database mode:**

| `DatabaseMode` | What you get | Cost after free tier | Notes |
|---|---|---|---|
| `local` (default) | Postgres 16 on the EC2 box | $0 extra | Data lives on the instance disk; nightly `pg_dump` backups (§12) |
| `rds` | RDS Postgres 16, db.t3.micro, 20 GB, 7-day automated backups | ~$15/mo | Stack takes ~15 min longer to create; a final snapshot is kept if you delete the stack |

## 5. Commit the production changes

The backend deploy ships **committed** code only (it uses `git archive`). Commit first:

```bash
git add -A
git commit -m "Add AWS free-tier production deployment"
```

## 6. Create the AWS stack

```bash
aws cloudformation deploy \
  --stack-name trackflow \
  --template-file deploy/cloudformation/trackflow.yaml \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides \
    KeyName=trackflow-key \
    UbuntuAmiId=$AMI_ID \
    InstanceType=t2.micro \
    SshCidr=$MY_IP/32 \
    DatabaseMode=local \
    DbPassword=$DB_PASSWORD \
    OriginSecret=$ORIGIN_SECRET \
    CloudFrontPrefixListId=$CF_PREFIX_LIST
```

- This takes **~5–10 min** (`local`) or **~15–20 min** (`rds`); most of the wait is CloudFront.
- If it fails with *"t2.micro is not supported in your requested Availability Zone"* or
  similar, delete the failed stack (`aws cloudformation delete-stack --stack-name trackflow`)
  and re-run with `InstanceType=t3.micro`.
- On failure, the console's **CloudFormation → trackflow → Events** tab shows which resource
  failed and why.

When it finishes, print the outputs:

```bash
aws cloudformation describe-stacks --stack-name trackflow \
  --query "Stacks[0].Outputs" --output table
```

Note `AppUrl` (your site) and `InstancePublicIp`.

The instance keeps provisioning in the background for ~3–5 minutes after the stack
completes (installing nginx, Redis, Postgres and creating swap). The next step waits for that
automatically.

## 7. Deploy the backend

```bash
SSH_KEY=~/.ssh/trackflow-key.pem ./deploy/scripts/deploy_backend.sh
```

The first run takes a few minutes (it creates the virtualenv). What it does:

1. `git archive` of `backend/` + `deploy/ec2/` at `HEAD` → uploads it to the instance
2. On the server (`server_deploy.sh`): waits for first-boot provisioning; writes your
   CloudFront hostname into `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`; `pip install`;
   `migrate`; `bootstrap` (creates issue types); `collectstatic`; installs the nginx site,
   systemd unit and backup cron; points `/srv/trackflow/current` at the new release;
   restarts; health-checks `/api/health/`
3. Keeps the last 5 releases for rollback (§13)

It should end with `==> Deploy complete: <release-id>`.

## 8. Create your admin account

```bash
ssh -i ~/.ssh/trackflow-key.pem ubuntu@<InstancePublicIp>
sudo trackflow-manage createsuperuser      # prompts for email, username, password
exit
```

> **Do not run `seed_demo` in production.** It creates demo users with the public password
> `password123`, one of them a superuser. Only use it on a throwaway demo stack.

## 9. Deploy the frontend

```bash
./deploy/scripts/deploy_frontend.sh
```

This builds `frontend/`, uploads it to the S3 bucket (hashed bundles cached for a year,
`index.html` never cached) and invalidates CloudFront.

## 10. Verify

Open the `AppUrl` output (`https://dxxxxxxxx.cloudfront.net`) and check:

- [ ] The login page loads, and signing in with the superuser from step 8 works
- [ ] Reloading a deep link (e.g. `/projects`) still loads the app (the SPA rewrite works)
- [ ] You can create a project and an issue (issue types exist)
- [ ] Chat: open it in two browsers; messages appear live (WebSockets through CloudFront work)
- [ ] You can upload an avatar or attachment and it displays (`/media/`)
- [ ] `/admin/` shows the Django admin with styling (`/static/`), and you can log in
- [ ] `/api/docs/` shows Swagger UI
- [ ] Hitting `http://<InstancePublicIp>/api/health/` directly **times out or returns 403**
      (the origin is locked to CloudFront)

## 11. (Optional) Auto-deploy from GitHub Actions

`.github/workflows/deploy.yml` always runs backend tests plus frontend build and tests on
pushes and PRs. The deploy job only runs on `main` once you enable it.

1. **Open SSH to GitHub's runners.** Their IPs change constantly, so update the stack to allow
   SSH from anywhere. Key-only auth still applies, and password login is disabled on Ubuntu
   AMIs.

   ```bash
   aws cloudformation deploy --stack-name trackflow \
     --template-file deploy/cloudformation/trackflow.yaml --capabilities CAPABILITY_IAM \
     --parameter-overrides SshCidr=0.0.0.0/0
   ```

   (Parameters you leave out keep their previous values.)

2. **Create a least-privilege IAM user** `trackflow-deployer` with this inline policy
   (replace `<BUCKET>` with the `FrontendBucketName` output and `<ACCOUNT_ID>` with yours),
   then create an access key for it:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       { "Effect": "Allow", "Action": "cloudformation:DescribeStacks", "Resource": "*" },
       { "Effect": "Allow", "Action": ["s3:ListBucket"], "Resource": "arn:aws:s3:::<BUCKET>" },
       { "Effect": "Allow", "Action": ["s3:PutObject", "s3:DeleteObject", "s3:GetObject"],
         "Resource": "arn:aws:s3:::<BUCKET>/*" },
       { "Effect": "Allow", "Action": "cloudfront:CreateInvalidation",
         "Resource": "arn:aws:cloudfront::<ACCOUNT_ID>:distribution/*" }
     ]
   }
   ```

3. In GitHub, go to **Settings → Secrets and variables → Actions**:
   - Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (the deployer user),
     `EC2_SSH_KEY` (the full contents of `trackflow-key.pem`)
   - Variables: `AWS_REGION` (e.g. `ap-south-1`), `DEPLOY_ENABLED` = `true`, and optionally
     `STACK_NAME` if it isn't `trackflow`
4. Push to `main`. It runs tests, then deploys the backend, then the frontend.

## 12. Backups

A cron job runs `trackflow-backup` nightly at 03:30 UTC. It writes a `pg_dump` and a tarball
of uploaded media to `/srv/trackflow/shared/backups/` and keeps 7 days.

**Those backups sit on the same disk as the app, so copy them off regularly:**

```bash
scp -i ~/.ssh/trackflow-key.pem "ubuntu@<IP>:/srv/trackflow/shared/backups/*" ./backups/
```

(They're root-only, so if `scp` is refused, first run
`ssh ... "sudo cp -r /srv/trackflow/shared/backups /tmp/b && sudo chown -R ubuntu /tmp/b"`
and then copy from `/tmp/b`.)

To run a backup now: `sudo trackflow-backup`. To restore a dump:

```bash
sudo systemctl stop trackflow
PGPASSWORD=<DB_PASSWORD> pg_restore --clean --if-exists -h <DB_HOST> -U trackflow -d trackflow db-XXXX.dump
sudo systemctl start trackflow
```

With `DatabaseMode=local`, **deleting the stack or terminating the instance deletes the
database.** Take and download a backup first.

## 13. Day-to-day operations

| Task | Command (on the server unless noted) |
|---|---|
| App logs (live) | `sudo journalctl -u trackflow -f` |
| nginx logs | `sudo tail -f /var/log/nginx/trackflow.access.log /var/log/nginx/trackflow.error.log` |
| First-boot log | `sudo less /var/log/cloud-init-output.log` |
| Restart the app | `sudo systemctl restart trackflow` |
| Django shell / any manage.py command | `sudo trackflow-manage shell` |
| Edit config/secrets | `sudo nano /srv/trackflow/shared/.env` then `sudo systemctl restart trackflow` |
| List releases | `ls -lt /srv/trackflow/releases/` |
| **Roll back** | `sudo ln -sfn /srv/trackflow/releases/<previous-id> /srv/trackflow/current && sudo systemctl restart trackflow` (only safe if that release's migrations are compatible) |
| OS security updates | Installed automatically (unattended-upgrades). Reboot occasionally: `sudo reboot` |
| Redeploy (from your PC) | `SSH_KEY=... ./deploy/scripts/deploy_backend.sh` / `./deploy/scripts/deploy_frontend.sh` |
| Your IP changed, SSH times out (from your PC) | `aws cloudformation deploy ... --parameter-overrides SshCidr=<new-ip>/32` (same flags as §11.1) |
| Shell without SSH | AWS console → EC2 → instance → **Connect → Session Manager** |

**Updating the stack:** re-run `aws cloudformation deploy` with the same template and only
the parameters you want to change. Don't change `UbuntuAmiId` casually: a new AMI
**replaces the instance**, and with `DatabaseMode=local` that loses the database.

**Tearing down:** download a backup, then
`aws s3 rm s3://<FrontendBucketName> --recursive` (a bucket must be empty to delete) and
`aws cloudformation delete-stack --stack-name trackflow`.

## 14. (Optional) Custom domain

1. In **ACM, region us-east-1** (CloudFront requires that region), request a public
   certificate for `app.example.com` and validate it with the DNS record ACM shows you.
2. Update the stack:

   ```bash
   aws cloudformation deploy --stack-name trackflow \
     --template-file deploy/cloudformation/trackflow.yaml --capabilities CAPABILITY_IAM \
     --parameter-overrides CustomDomainName=app.example.com \
       AcmCertificateArn=arn:aws:acm:us-east-1:<ACCOUNT_ID>:certificate/<ID>
   ```

3. At your DNS provider, add `CNAME app.example.com → dxxxxxxxx.cloudfront.net` (use a Route 53
   alias record if you use Route 53).
4. Re-run `deploy_backend.sh` so Django accepts the new hostname (it reads the `AppDomains`
   output).

## 15. Troubleshooting

| Symptom | Likely cause and fix |
|---|---|
| `502 Bad Gateway` / `504` from CloudFront | App not running or not deployed yet. Run `sudo systemctl status trackflow` and `journalctl -u trackflow -n 100`. Before the first backend deploy this is expected. |
| `403` on every API call | nginx didn't get the right `X-Origin-Verify`. Check that `ORIGIN_SECRET` in `.env` matches the stack's `OriginSecret`, then redeploy the backend (it re-renders nginx.conf). |
| `400 Bad Request` from Django | Host isn't in `ALLOWED_HOSTS`. Redeploy the backend (it syncs hosts from the stack outputs) or edit `.env`. |
| Admin login fails with "CSRF verification failed" | Same fix: `CSRF_TRUSTED_ORIGINS` must contain `https://<your domain>`. |
| Chat shows "connecting…" forever | Check `journalctl -u trackflow` for WebSocket errors; confirm `CHANNEL_LAYER=redis` in `.env` and that `systemctl status redis-server` is active. |
| Frontend still shows the old version | Hard-refresh. `index.html` is uncached, but the invalidation can take 1–2 minutes. |
| `deploy_backend.sh`: *Permission denied (publickey)* | Wrong key path, or you're using `ec2-user` instead of `ubuntu`. |
| `deploy_backend.sh` hangs at "Uploading" | Your IP changed; update `SshCidr` (§13). |
| `WARNING: UNPROTECTED PRIVATE KEY FILE` (Windows OpenSSH) | In PowerShell: `icacls $HOME\.ssh\trackflow-key.pem /inheritance:r /grant:r "$($env:USERNAME):R"` |
| Stack fails on `Database`: engine version not available | AWS retired that minor version. Run `aws rds describe-db-engine-versions --engine postgres --query "DBEngineVersions[?starts_with(EngineVersion,'16')].EngineVersion"` and set `EngineVersion` in the template to a listed 16.x version. |
| Instance slow or out of memory | `free -h`. The micro box has 1 GB RAM + 2 GB swap. Lower `--workers` in `deploy/ec2/trackflow.service` to 1, or move to t3.small (not free). |

## Security notes and known limitations

- **Uploaded files are public by URL** (`/media/...`), as they were in development. URLs are
  hard to guess but not signed. nginx serves them with a sandboxing CSP so an uploaded
  HTML/SVG can't run script on the app's origin.
- **Anyone can sign up** at `/signup`. Disable or restrict signup in the backend if this
  should be private.
- **Single instance:** no load balancer or auto-healing. If the instance dies, the site is
  down until you start or replace it. That's the trade-off for staying free.
- **Celery** runs in eager mode (`CELERY_TASK_ALWAYS_EAGER=True`). The app defines no
  background tasks today, so no worker process is needed.
- **HSTS is off by default.** Once you're sure the site will only ever be served over HTTPS,
  set `SECURE_HSTS_SECONDS=31536000` in `.env` and restart.
