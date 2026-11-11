# Operations

## Local API and worker

Run the API and worker in separate terminals. They share the same DATABASE_URL and session-independent database. The worker needs provider and embedding credentials because collection and indexing run in the worker process.

## PostgreSQL

Use PostgreSQL with the pgvector extension. Docker Compose uses the pgvector/pgvector:pg16 image. Alembic creates the schema and extension on first startup.

Back up the database volume regularly. Backups should include the database and any future external object-storage bucket. Test restores, not only backup creation.

## Production checklist

- Set a unique high-entropy SESSION_SECRET_KEY.
- Set AUTH_COOKIE_SECURE=true behind HTTPS.
- Set a strong database password; avoid special URL characters unless the connection URL is percent-encoded.
- Restrict the database to the private network.
- Add edge rate limits for account registration, login, research creation, URL imports and document uploads.
- Set reverse-proxy request-body limits and outbound network restrictions.
- Configure structured logs, error monitoring and uptime checks.
- Rotate provider keys and session secrets with a planned session invalidation window.
- Configure a tested backup and restore schedule.
- Do not store high-risk confidential documents until a security review, privacy policy and data-retention rules are in place.

## Worker operations

The worker logs job IDs, project IDs, attempts and completion counts. It does not log document bodies or API keys. Jobs retry up to three attempts. Rows left in running are requeued or failed when a worker starts after their lease becomes stale.

Run multiple worker replicas only on PostgreSQL. A local SQLite setup should use one worker process.
