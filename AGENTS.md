# Coding agent instructions

- Preserve the locked architecture: React/TypeScript/Vite, Django modular monolith/DRF/Channels, PostgreSQL/PostGIS, Redis/Celery, and Mosquitto.
- React must use Django REST or WebSocket interfaces and must never access the database directly.
- Work on feature branches; `main` is stable and changes require a pull request and another team member's review.
- Preserve user changes. Never use destructive Git commands or force-push.
- Never commit secrets, real credentials, `.env`, or production keys.
- Add tests for changes and run relevant lint, type-check, test, build, Django, migration, and Compose checks before committing.
- Do not describe planned functionality as implemented.
- Keep business capabilities out of foundation work until their approved sprint.
