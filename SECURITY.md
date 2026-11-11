# Security policy

Nexus Research is an early MVP. Do not expose it to the public internet with sensitive research or credentials until authentication, per-user authorization, rate limiting, secure deployment configuration, and a production database have been implemented and reviewed.

## Reporting a vulnerability

Please do not publish exploitable security details in a public issue. Contact the repository owner privately through GitHub's security advisory feature, if enabled, or use a private communication channel.

## Current security boundaries

- Provider keys are read server-side from environment variables.
- `.env` and local database files are excluded from Git.
- URL import rejects localhost/private/reserved destinations, supports only HTTP(S), avoids redirects, and caps response size.
- File uploads are type- and size-limited, but extracted document content may contain untrusted instructions. The AI prompt is designed to treat it as evidence, not instructions; review generated output.
- The application currently has no end-user authentication or multi-tenant data isolation. Run locally or behind a trusted private network only.
