# Development workflow

`main` is the stable branch. Do not develop features directly on it.

1. Synchronize `main` using fast-forward only.
2. Create a narrowly scoped feature branch.
3. Add tests and run all relevant CI-equivalent checks.
4. Open a pull request targeting `main`.
5. Require another project member to review before merge.

Required CI checks include frontend lint, type-check, tests, and build; backend lint, Django checks, migration drift check, and tests against PostGIS; and Compose configuration validation.

Use Conventional Commits, for example:

- `chore: configure local development services`
- `feat: add vehicle registration`
- `fix: handle unavailable database in health check`
- `docs: clarify telemetry units`

Never force-push shared branches or commit credentials.
