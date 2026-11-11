# Security policy

Nexus Research V2 includes authenticated accounts and owner-scoped persistence, but it is not an independently audited security product.

## Supported baseline

- Passwords are hashed using Argon2.
- Session cookies are HttpOnly, SameSite=Lax and configurable as Secure.
- Authenticated writes require a signed CSRF token.
- All project, source, report, message and job queries are scoped to the current account.
- Provider keys are read server-side.
- .env, local databases and local data directories must not be committed.
- URL imports reject localhost/private/reserved destinations and redirects; deploy with outbound network restrictions to reduce SSRF risk.
- Uploaded content and retrieved passages are treated as untrusted data by the AI prompts.

## Known security gaps

- Email verification, password reset, MFA, OAuth, organization roles, audit logs and account deletion workflows are not implemented.
- Application-level distributed rate limiting is not implemented; enforce it at the reverse proxy or API gateway before public exposure.
- DNS rebinding and parser-specific document attacks require further hardening and review.
- There is no independent penetration test or security certification.

## Reporting

Do not publish exploitable details in public issues. Use GitHub's private vulnerability reporting when enabled, or contact the repository owner privately.
