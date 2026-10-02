# Abera Dograh tenant runtime (DEV)

This Compose profile runs **one subscription per EC2 instance**. The ALB
terminates TLS and forwards to port 8080; the instance security group must
accept that port only from the ALB. API, UI, Valkey and workers are private to
the Compose network. PostgreSQL is external and each subscription uses its
own database login. S3 access comes from the instance role.

## Required deployment inputs

The control plane writes a root-owned, mode-0600 runtime env file on an
encrypted EBS volume. It supplies `DATABASE_URL` (tenant DB and restricted
role), `REDIS_URL`, `OSS_JWT_SECRET` and other backend secrets. A second
mode-0600 file, supplied only to the one-shot `provision` process, contains
`ABERA_ADMIN_EMAIL` and `ABERA_ADMIN_PASSWORD`. The initial password must
match the one-time credentials envelope held by Automations.

Set these Compose variables from the subscription record, never from a
browser request:

- `ABERA_SUBSCRIPTION_ID`, `ABERA_PLAN` (`basic` or `pro`),
  `ABERA_MAX_AGENTS`, `ABERA_MAX_CONCURRENT_CALLS`,
  `ABERA_STORAGE_LIMIT_BYTES` (decimal GB × 1,000,000,000),
  `ABERA_MANAGED_NOVA_ENABLED`.
- `PUBLIC_HOST`, `PUBLIC_BASE_URL`, `FORWARDED_ALLOW_IPS`.
- `S3_BUCKET`, `S3_REGION`, `REDIS_PASSWORD`,
  `ABERA_RUNTIME_ENV`, `ABERA_PROVISION_ENV`.
- `DOGRAH_API_IMAGE`, `DOGRAH_UI_IMAGE`, `VALKEY_IMAGE` and
  `NGINX_IMAGE`, all pinned to immutable digests.

The runtime env file must use a PostgreSQL TLS connection string. The
instance role needs access only to this subscription's S3 prefix and, for
Pro, invocation of Nova 2 Sonic in `us-east-1`.

## Provision or update

The control plane performs these steps under a per-subscription operation
lock:

1. Close ingress and wait for active voice sessions to finish.
2. Run `docker compose -f compose.yaml run --rm migrate` exactly once.
3. Run `docker compose -f compose.yaml run --rm provision`. It is safe to
   retry and does not reset a changed password.
4. Start the long-running services with
   `docker compose -f compose.yaml up -d valkey api worker orchestrator ui gateway`.
5. Check API health and ALB target health before reopening ingress.

The `ari` profile is used only after the customer configures an ARI
provider. Valkey AOF lives at `/var/lib/abera/redis` on persistent encrypted
storage. Backups and replacements must preserve or restore this path.

## Call recordings

Basic does not start audio recording or retain mixed, caller or agent tracks.
Transcripts and call logs remain available. Pro captures the three tracks in
bounded buffers that spill to the encrypted instance disk, writes WAV files in
chunks, and uploads them from the same process with the storage file-transfer
API. Temporary files are removed after upload, including failed uploads.
The completion job waits for the upload because QA and webhooks inspect the
recording metadata. This does not require Lambda or a shared filesystem.

This profile does not itself schedule backups or grant minutes. Pro voice
calls fail closed until Billing's reservation endpoint is connected.
