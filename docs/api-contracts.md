# API contracts

## `GET /api/health/`

Implemented readiness endpoint. It performs a lightweight database query.

Successful response (`200 OK`):

```json
{
  "status": "ok",
  "service": "ftms-backend",
  "database": "ok"
}
```

Unavailable database response (`503 Service Unavailable`):

```json
{
  "status": "error",
  "service": "ftms-backend",
  "database": "unavailable"
}
```

The response intentionally excludes credentials, environment values, internal hostnames, and stack traces.

`/api/v1/` is reserved for future FTMS business APIs. No business endpoints are implemented.
