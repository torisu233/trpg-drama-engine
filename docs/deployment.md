# Deployment: CI/CD to the cloud

> **Status: the hosted services have been shut down.** There is no live URL. The CI `deploy` job is disabled and only runs when the repository variable `DEPLOY_ENABLED` is set to `'true'`; the `test` job still runs on every push and pull request. This document records how the deployment worked so it can be reproduced.

The project was deployed in two phases, both driven by the same GitHub Actions pipeline (`git push master` -> test -> build -> push image -> deploy):

1. **AWS phase**: ECR + ECS Express Mode + RDS PostgreSQL in a custom VPC, with keyless deploys via GitHub OIDC.
2. **GCP phase** (from 2026-06): Artifact Registry + Cloud Run + Cloud SQL PostgreSQL, with keyless deploys via Workload Identity Federation.

The application itself did not change between phases: `config.py` and Alembic read `DATABASE_URL` directly, so moving clouds only touched the workflow, the Dockerfile and this document.

### Why it moved to GCP
The migration commit does not record one specific trigger, but the differences that mattered for a low-traffic demo are documented below:
- **Cost model**: Cloud Run scales to zero and bills nothing while idle, whereas ECS Express (Fargate + ALB) bills for as long as the service exists, which meant tearing it down between demos.
- **Less networking**: Cloud Run reaches the internet directly and connects to Cloud SQL through the built-in connector (a unix socket), so there is no VPC, subnet or security-group setup to maintain.

Shared pieces (both phases): the container image, migrations on startup, the GitHub Variables/Secrets pattern, and the principle that server-side secrets never reach the frontend, the repo or the image.

---

## Pipeline

### GCP phase (final)
```
git push master
   │
   ├─ test    pytest (against a Postgres service container in CI; never calls the LLM)
   └─ deploy  [only if vars.DEPLOY_ENABLED == 'true']
              WIF -> short-lived GCP credentials -> docker build
              -> push to Artifact Registry (tags: latest + git sha)
              -> gcloud run deploy (--add-cloudsql-instances mounts the Cloud SQL socket,
                 runs as the runtime service account, injects env vars)
              -> container starts with `alembic upgrade head`, then uvicorn
Pull requests / other branches: test only (CD runs only from master)
```

### AWS phase (earlier)
```
git push master
   │
   ├─ test            pytest (Postgres service container; never calls the LLM)
   ├─ build-and-push  OIDC -> assume IAM role -> docker build -> push to ECR (tags: latest + git sha)
   └─ deploy          OIDC -> aws-actions/amazon-ecs-deploy-express-service
                      -> create/update the ECS Express service (custom VPC public subnets + app security group)
                      -> container starts with `alembic upgrade head`, then uvicorn
Pull requests / other branches: test only
```

Defined in [`.github/workflows/ci.yml`](../.github/workflows/ci.yml). The pattern is **registry-driven**: GitHub Actions does CI, builds the image, pushes it to the registry and triggers the deploy; the container platform (ECS, then Cloud Run) runs it.

## Key design: no long-lived cloud keys
CI stores no static cloud credentials in either phase. On each run GitHub issues a short-lived OIDC token, which is exchanged for temporary credentials:
- **AWS**: the workflow assumes an IAM role via GitHub OIDC (`sts:AssumeRoleWithWebIdentity`). No AWS access keys in GitHub.
- **GCP**: the OIDC token is federated through **Workload Identity Federation** to impersonate a deploy service account. No service-account key files in GitHub.

---

## GCP phase

### Resources (project `<GCP_PROJECT_ID>` / number `<GCP_PROJECT_NUMBER>` / region `asia-northeast1`)
| Resource | Name | Purpose |
|---|---|---|
| Artifact Registry (Docker) | `trpg` | Stores images; path `asia-northeast1-docker.pkg.dev/<GCP_PROJECT_ID>/trpg/trpg` |
| Cloud Run service | `trpg` (created on first deploy) | Runs the container, serves public HTTPS on `*.run.app`, scales to zero |
| Cloud SQL Postgres 16 | `trpg-pg` (db-f1-micro, zonal, no backups) | Single source of truth (users / scenarios / games / feedback); database `trpg`, user `trpg` |
| Connection name | `<GCP_PROJECT_ID>:asia-northeast1:trpg-pg` | Used by `--add-cloudsql-instances` and the socket-style `DATABASE_URL` |
| Runtime service account | `trpg-run@<GCP_PROJECT_ID>.iam.gserviceaccount.com` | Identity Cloud Run runs as; `roles/cloudsql.client` |
| Deploy service account | `trpg-deployer@<GCP_PROJECT_ID>.iam.gserviceaccount.com` | Impersonated by GitHub; `run.admin` + `artifactregistry.writer` + `iam.serviceAccountUser` (actAs) on the runtime SA |
| WIF pool / provider | `github-pool` / `github-provider` | Trusts GitHub OIDC; `attribute-condition` restricts `repository_owner` to `<GITHUB_OWNER>`, and the principalSet is bound to `<GITHUB_OWNER>/trpg-drama-engine` |

### No VPC or network configuration needed
- Cloud Run is fully managed and has direct outbound internet access (to pull from Artifact Registry and call the LLM API), so **no NAT and no custom VPC**.
- Cloud SQL is reached through the **built-in connector** (`--add-cloudsql-instances` mounts a unix socket at `/cloudsql/<connection name>`), so **no private IP and no Serverless VPC Access connector**. This is considerably simpler than the AWS setup with its own public/private subnets.

### Secrets and configuration (GitHub -> Cloud Run env vars)
Repository Settings -> Secrets and variables -> Actions:

**Variables** (plain text, `${{ vars.X }}`): `DEPLOY_ENABLED`, `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_WIF_PROVIDER`, `GCP_DEPLOY_SA`, `GCP_RUN_SA`, `GCP_SQL_CONN`, `GCP_IMAGE`, `ADMIN_USERNAME`.

**Secrets** (encrypted, `${{ secrets.X }}`):
| Secret | Purpose |
|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://trpg:<password>@/trpg?host=/cloudsql/<GCP_PROJECT_ID>:asia-northeast1:trpg-pg` (socket form; avoid URL special characters in the password or percent-encode them) |
| `JWT_SECRET` | Signs and verifies JWTs (`python3 -c "import secrets; print(secrets.token_hex(32))"`) |
| `ADMIN_PASSWORD` | Seeds the initial admin on first startup against an empty database |
| `LLM_API_KEY` | Server-side key for the LLM provider (DeepSeek) |

- Injected with `gcloud run deploy --set-env-vars`, using `^~^` to change the delimiter so the `= / @ :` characters in `DATABASE_URL` aren't misparsed. The values are stored in plain text in the Cloud Run service configuration (visible only inside the project); this tradeoff was accepted for flexibility. To harden it, switch to **Secret Manager + `--set-secrets`**.
- Architecture principle: **externally, users authenticate with JWTs; internally, the LLM key and database password are server-side secrets** that never reach the frontend, the repo or the image.

### Concurrent migrations
When Cloud Run scales from zero or runs several instances, the first cold start runs the migration. Several instances starting at once can race slightly (Alembic is idempotent, so the risk is low). To harden it, run migrations as a separate CI step before deploying, or use a Cloud Run Job or a Postgres advisory lock.

### Deploying and verifying
- **Automatic** (when enabled): push to `master` -> CI `test` passes -> `deploy` builds, pushes to Artifact Registry and runs `gcloud run deploy`.
- Service URL: printed at the end of the `deploy` job, or `gcloud run services describe trpg --region asia-northeast1 --format='value(status.url)'`.
- Verify: `/` (the SPA; register or log in to enter), `/api/health` -> `{"ok":true}`, register an account, and play a game (requires `LLM_API_KEY` to be injected).

### Cost and teardown
- **Cloud Run scales to zero**: no charge without requests (cheaper than an always-on ECS service); `--max-instances 3` caps it.
- **Cloud SQL bills continuously**: db-f1-micro is roughly $8-10/month (covered by free-trial credit at the time). **Deleting the Cloud Run service does not affect Cloud SQL**; the data lives in the database. Delete it only when it's no longer needed: `gcloud sql instances delete trpg-pg`.
- Artifact Registry charges a small amount for storage (the image is small). Delete the service with `gcloud run services delete trpg --region asia-northeast1`.

### One-time GCP setup (to reproduce, from Cloud Shell)
Enable the APIs (run, artifactregistry, sqladmin, iam, iamcredentials, sts, cloudresourcemanager) -> create the Artifact Registry repository -> create the Cloud SQL instance, database and user -> create the two service accounts and grant their roles -> create the WIF pool and provider and bind the repository -> set the Variables and Secrets above in GitHub.

---

## AWS phase

### Resources (account `<AWS_ACCOUNT_ID>` / region `ap-northeast-1`)
| Resource | Name | Purpose |
|---|---|---|
| ECR private repository | `<ECR_REPOSITORY>` | Stores Docker images |
| OIDC provider | `token.actions.githubusercontent.com` | Lets AWS trust GitHub Actions |
| CI role | `github-actions-deploy-role` | Assumed by GitHub via OIDC; trust policy limited to `repo:<GITHUB_OWNER>/*` |
| └ managed policy | `AmazonEC2ContainerRegistryPowerUser` | Push to ECR |
| └ inline policy | `ecs-express-deploy` | 12 `ecs:*` deploy actions + `iam:PassRole` (only for the two roles below, only to ECS) |
| ECS task execution role | `ecsTaskExecutionRole` (service-role path) | ECS pulls images and writes logs |
| ECS infrastructure role | `ecsInfrastructureRoleForExpressServices` | Lets Express Mode provision the ALB and networking |
| ECS Express service | `trpg` (cluster `default`) | Runs the container and exposes a public HTTPS URL |
| VPC | created with the console wizard: 2 AZs, 2 public + 2 private subnets, **no NAT gateway** | Isolates the app from RDS |
| App subnets (2 public) | one per AZ | Run the ECS tasks (public IPs, outbound via the internet gateway to pull from ECR and call the LLM API) |
| App security group | `trpg-app-sg` | Attached to the tasks; RDS only accepts traffic from it |
| RDS security group | `trpg-rds-sg` | Inbound 5432 only from the app security group |
| DB subnet group | `trpg-db-subnets` (2 private subnets) | Places RDS in private subnets |
| RDS Postgres 16 | `trpg-db` (db.t4g.micro, not publicly accessible, database `trpg`) | Single source of truth (users / scenarios / games) |

The public URL had the form `https://<service-id>.ecs.ap-northeast-1.on.aws/` (the ALB hostname changes when the service is recreated).

### Network architecture: app in public subnets, RDS in private subnets, same VPC, no NAT
```
              Internet
                 │  [Internet Gateway]
 ┌───────────────┴──── VPC (DNS hostnames / resolution enabled) ──────────────────┐
 │  Public subnets x2 AZ                         Private subnets x2 AZ             │
 │  ┌──────────────────────────┐                ┌────────────────────────────┐    │
 │  │ Express: ALB + Fargate    │                │  RDS Postgres 16            │    │
 │  │ tasks have public IPs     │──── 5432 ─────▶│  publicly accessible: no    │    │
 │  │ (pull ECR / call LLM),    │  app-SG ->     │  RDS-SG inbound only from   │    │
 │  │ attached to app-SG        │  RDS-SG        │  app-SG                     │    │
 │  └──────────────────────────┘                └────────────────────────────┘    │
 └──────────────────────────────────────────────────────────────────────────────┘
      No NAT gateway: the app needs outbound access and sits in public subnets
      with a direct route to the IGW; RDS needs no outbound access at all.
```
- **Explicit subnets**: the deploy action passes `subnets` (the two public subnets), so Express creates an internet-facing ALB and gives tasks `assignPublicIP=true`. Only private subnets would require a NAT gateway.
- **Saves about $33/month on NAT**: the component that needs outbound access (the app) is in a public subnet with a direct route to the internet gateway; the component that must be hidden (RDS) is in a private subnet and never goes outbound. Neither needs NAT.
- **Security group to security group**: a self-managed `app-SG` is attached to the tasks (a known, fixed id, which avoids the chicken-and-egg problem with the security group Express would otherwise create), and `RDS-SG` allows inbound 5432 only from `app-SG`. RDS is never exposed to the internet.
- **VPC requirements**: at least 2 public subnets (the Express ALB spans 2 AZs) and at least 2 private subnets (an RDS subnet group needs 2 AZs); `enableDnsHostnames` and `enableDnsSupport` must be on.

### Secrets and configuration (environment variables, deliberately not Secrets Manager)
All values were stored as **GitHub repository secrets** and injected by the deploy action:

| Secret | Injected as | Purpose |
|---|---|---|
| `LLM_API_KEY` | env | Server-side key for the LLM provider (DeepSeek) |
| `DATABASE_URL` | env | `postgresql+psycopg2://...@<RDS endpoint>:5432/trpg` (includes the database password) |
| `JWT_SECRET` | env | Signs and verifies JWTs (at least 32 random bytes; e.g. `openssl rand -base64 48`) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | env | Seed the initial admin on first startup against an empty database |
| `APP_SUBNETS` | action `subnets` | The two public subnet ids (comma-separated); not sensitive, stored as a secret only to avoid hard-coding |
| `APP_SG` | action `security-groups` | The app security group id |

- **No AWS Secrets Manager**: rotating a key only means changing a GitHub secret, without touching AWS. The accepted tradeoff is that values are stored in plain text in the task definition (visible only within the account). Per the AWS docs, plain `environment-variables` require **no** Secrets Manager permissions on the execution role.
- The old shared `APP_PASSWORD` gate was **replaced by user auth and removed** (middleware, config, env vars and publish script).

### Container notes specific to ECS
- **Gotcha: ECS Express defaults to container port 80.** It must be set to `container-port: 8080`; otherwise the ALB health check hits port 80 while the container listens on 8080 and the target is marked unhealthy. A non-root process can't bind port 80 (privileged), so the fix is to align ECS with 8080, not to change the app.
- Health check path: `/api/health` (unauthenticated, very cheap, independent of the frontend).
- With a single task (Express default `minTask=1`) there is no migration race; scaling to multiple tasks would need a migration gate or a one-off migration task.

### Cost and teardown
- **ECS Express = Fargate + ALB, billed while running.** Demo workflow: deploy -> capture screenshots or a recording -> **delete the service** (ECS -> `default` -> `trpg` -> Delete, which also removes the ALB). Pushing again recreates it.
- **RDS bills separately** (db.t4g.micro is in the first-year free tier; roughly $12-15/month plus storage afterwards). **Deleting the ECS service does not affect RDS**, so data survives redeploys. Delete it only when no longer needed: `aws rds delete-db-instance --db-instance-identifier trpg-db --skip-final-snapshot --delete-automated-backups`.
- **VPC, subnets and security groups are free** (NAT is the expensive part, and none was created).
- Budget alerts were configured as a safety net.

### Lessons learned
- **App Runner stopped accepting new customers on 2026-04-30**, so the deployment used **ECS Express Mode** instead (the official replacement, which runs ECR images).
- Container port 80 vs. the app's 8080 (see above).
- IAM deploy permissions: the action actually needs 12 `ecs` actions (including `ListServiceDeployments` / `DescribeServiceDeployments` / `TagResource` / `UntagResource`, used to poll deployment progress and tag resources). Missing any of them causes `AccessDenied` at the "wait for deployment" step. `iam:PassRole` must be granted explicitly and scoped with `iam:PassedToService=ecs.amazonaws.com`.

---

## Shared: container and migrations

### Database migrations at container startup
- The container command is `alembic upgrade head && exec uvicorn ...`: every startup first brings the schema up to date (**idempotent**: creates tables on an empty database, no-op when already current), then starts the server. `config.py` and `alembic/env.py` both read `DATABASE_URL` directly, so the Cloud SQL socket form works unchanged.
- After the first deploy the environment automatically has all four tables plus the seeded admin (from `ADMIN_*`). Scenarios are not seeded; users create them through the authoring page.
- The Dockerfile must `COPY` `alembic.ini` and `alembic/`, or there is nothing to migrate inside the container.

### Dockerfile
- Listens on `0.0.0.0:${PORT:-8080}` (Cloud Run injects `PORT=8080`); runs as a **non-root** user.
- Multi-stage build: a Node stage only builds the frontend `dist`; the final image contains just Python, the backend and `dist`. `main.py` serves `dist` and `/api` from the same origin.
- The command uses exec form so uvicorn receives SIGTERM and shuts down cleanly.

## Known limitations / possible hardening
- **Secrets**: the database password, JWT secret and LLM key were stored in plain text in the service configuration (Cloud Run env vars / ECS task definition). Move to Secret Manager (`--set-secrets`) or AWS Secrets Manager / RDS IAM auth.
- **Database TLS**: on GCP, the Cloud SQL connector (socket) is encrypted within Google's network, so no extra `sslmode` was configured. On AWS, `DATABASE_URL` did not enforce `sslmode=require`; RDS sat in private subnets so the exposure was small, but production should require it.
- **JWT access tokens only**: no refresh tokens or revocation list; users log in again after 7 days.
- **Migration concurrency**: multiple instances cold-starting at once can race on migrations (see above).
