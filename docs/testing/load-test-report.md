# FTMS Controlled Load-Test Report

## Status

Run not performed. This repository now includes an evaluator-ready k6 workload, but k6 was not installed in the audited environment on 2026-09-24. No result numbers are reported or inferred.

Use this document as the result template for a **controlled capstone staging/local load test**. It must not be presented as proof of production scalability.

## Reproducible command

Run only against an isolated local or staging database. Use a dedicated active staff account that has access to the selected read endpoints and does not require 2FA.

```bash
BASE_URL=http://localhost:8000 \
TEST_USERNAME='<staging-user>' \
TEST_PASSWORD='<staging-password>' \
SUMMARY_PATH=load-test-summary.json \
k6 run load-tests/ftms-read-load.js
```

Credentials are supplied at runtime and must never be committed. Set `TEST_DEVICE_ID` to include one known test vehicle's latest-status read. Set `INCLUDE_REPORTS=true` only when the test account has report access. Durations and VU targets can be overridden through `STAGE_1_DURATION` through `STAGE_4_DURATION`, `RAMP_DOWN_DURATION`, and `STAGE_1_VUS` through `STAGE_4_VUS`.

## Test definition

| Item | Value |
|---|---|
| Date/time | Not run |
| Environment | Local/staging only; record exact host here |
| Hardware/VM/container details | Record CPU, RAM, OS, Docker limits, and topology here |
| Authentication | Django session login established once during k6 setup using CSRF; session cookie shared by read-only VUs |
| Profile | Ramp to 10 VUs/30s, 25 VUs/60s, 50 VUs/60s, 100 VUs/60s, then ramp down/30s |
| Think time | 1 second by default; configurable |
| Workload | Concurrent HTTP GET requests only |

### Endpoints

- `GET /api/health/`
- `GET /api/v1/dashboard/summary/`
- `GET /api/v1/transport-requests/?page=1&page_size=20`
- `GET /api/v1/fleet-live/vehicles/`
- Optional when `TEST_DEVICE_ID` is provided: `GET /api/v1/vehicles/{device_id}/latest-status/`
- `GET /api/v1/auth/notifications/?page=1&page_size=20`
- Optional: `GET /api/v1/reports/transport-requests/?page=1&page_size=15`

No dispatch, approval, maintenance, pairing, permission, SOS, account, or other state-changing endpoint is called. Telemetry ingestion is omitted because the audit did not establish an isolated test-device identity. WebSocket load is omitted to keep the primary evidence reproducible and HTTP-focused.

## Evaluation thresholds

These are capstone evaluation thresholds, not contractual production SLAs:

- Overall read error rate: less than 1%
- Ordinary read endpoint p95: less than 2,000 ms
- Dashboard and optional report p95: less than 3,000 ms

## Results

Populate this table only from the generated `load-test-summary.json` and k6 terminal output.

| Metric | Actual result | Threshold/result |
|---|---:|---|
| Total requests | Not run | Informational |
| Requests/second | Not run | Informational |
| Success rate | Not run | Informational |
| Error rate | Not run | `< 1%` |
| p50 latency | Not run | Informational |
| p95 latency | Not run | `< 2,000 ms` ordinary reads |
| p99 latency | Not run | Informational |
| Maximum latency | Not run | Informational |
| HTTP 2xx count | Not run | Informational |
| HTTP 3xx count | Not run | Investigate if non-zero |
| HTTP 4xx count | Not run | Investigate if non-zero |
| HTTP 5xx count | Not run | Investigate if non-zero |

### Observed errors

Not run. Record endpoint-tagged failures and representative server logs without credentials, cookies, or personal data.

### Interpretation

Not yet available. State whether each capstone threshold passed, identify the first load stage where degradation appeared, and distinguish permission/configuration failures from server errors.

## Supporting observations

During the run, capture these separately if available:

```bash
docker stats --no-stream
docker compose exec db psql -U ftms -d ftms -c "select count(*) from pg_stat_activity;"
docker compose exec redis redis-cli ping
docker compose exec celery celery -A config inspect ping
```

These commands are observational. Record their timestamps and outputs in the final evaluator evidence; do not place credentials in the report.

## Limitations

- A local/staging result does not establish production scalability or capacity.
- One pre-authenticated authoritative staff session is shared across VUs, matching FTMS single-session enforcement but not measuring concurrent login or 2FA verification.
- Results depend on test-data volume, host resources, container limits, database state, and enabled permissions.
- Browser rendering, external map/search providers, MQTT, Celery task throughput, telemetry writes, and WebSocket fan-out are outside this test.
- The fixed first page validates concurrent list reads, not deep pagination behavior.
