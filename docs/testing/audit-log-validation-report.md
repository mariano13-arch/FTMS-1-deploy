# Centralized Audit Log Validation Report

## Purpose

Phase 1 implements a centralized, evaluator-ready audit trail for security and Users & Access administration so FTMS records user activities with timestamps and user identification.

## Scope

Implemented in Phase 1:

- Authentication and session audit events.
- MFA and password security audit events.
- Staff account, invitation, role, status, and permission-matrix audit events.
- Fleet Admin-only read-only API and UI.

Deferred to Phase 2:

- Vehicles, drivers, devices, settings, maintenance, inspection corrections, and selected dispatch override/reassignment central audit hooks.

## Phase 1 Action Catalog

- `LOGIN_SUCCESS`
- `LOGIN_FAILURE`
- `ACCOUNT_LOCKED`
- `ACCOUNT_LOCK_EXPIRED`
- `LOGOUT`
- `SESSION_REVOKED`
- `PASSWORD_CHANGED`
- `PASSWORD_RESET_COMPLETED`
- `MFA_ENABLED`
- `MFA_DISABLED`
- `MFA_DISABLE_REJECTED`
- `RECOVERY_CODE_USED`
- `STAFF_CREATED`
- `STAFF_INVITED`
- `STAFF_ROLE_CHANGED`
- `STAFF_STATUS_CHANGED`
- `ROLE_PERMISSIONS_REPLACED`

## AuditEvent Schema

`AuditEvent` stores `occurred_at`, nullable `actor`, `actor_type`, `action`, target fields, `outcome`, `source`, safe request context (`ip_address`, trimmed `user_agent`), allowlisted `changes`, and sanitized `metadata`.

Useful indexes are provided for the audit table default order and supported filters: occurred time, actor/time, action/time, and target type/id.

## RBAC

Only `FLEET_ADMIN` can view centralized audit logs in Phase 1. Fleet Manager, Dispatcher, Fleet Staff, and Driver identities are denied by backend enforcement.

## Redaction Rules

Audit metadata is allowlist-oriented and helper-sanitized. It must not store passwords, password hashes, TOTP secrets, provisioning URIs, recovery codes, reset/setup tokens, session keys, CSRF tokens, Authorization headers, API/device credentials, SMTP credentials, TomTom keys, database credentials, raw request bodies, or uploaded file contents.

## Immutability

Audit events are append-only at application level. Internal creation is allowed; update and delete raise `ValueError`. The public API exposes no write endpoints. This is not database-level tamper proofing.

## API And Filters

Endpoint: `GET /api/v1/auth/audit-logs/`

Filters:

- `occurred_after`
- `occurred_before`
- `actor`
- `action`
- `target_type`
- `outcome`
- `page`
- `page_size`

Ordering is newest first.

## Tests Executed

Record results in the implementation handoff after running focused backend and frontend checks.

## Evaluator Demo

Use genuine activity created after implementation:

1. Log in as Fleet Admin.
2. Open Users & Access -> Audit Logs and show `LOGIN_SUCCESS`.
3. Create or invite a test staff account.
4. Change that account role or active status.
5. Return to Audit Logs and show timestamp, actor, action, target, and result.
6. Open Details and show old/new state.
7. Filter by action.
8. Confirm no password/token/secret values are present.
9. Demonstrate a non-Fleet-Admin account is denied.

## Limitations

Phase 1 intentionally does not centralize telemetry samples, dashboard polling, normal GET requests, ordinary trip progress, normal geofence enter/exit events, notifications, or broad domain histories.
