import http from "k6/http";
import { check, fail, sleep } from "k6";
import { Counter, Rate, Trend } from "k6/metrics";

const baseUrl = (__ENV.BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const username = __ENV.TEST_USERNAME;
const password = __ENV.TEST_PASSWORD;
const sessionCookieName = __ENV.SESSION_COOKIE_NAME || "sessionid";
const thinkTimeSeconds = Number(__ENV.THINK_TIME_SECONDS || "1");
const includeReports = (__ENV.INCLUDE_REPORTS || "false").toLowerCase() === "true";
const testDeviceId = __ENV.TEST_DEVICE_ID;

const requestErrors = new Rate("ftms_read_errors");
const requestSuccess = new Rate("ftms_read_success");
const readLatency = new Trend("ftms_read_latency", true);
const dashboardLatency = new Trend("ftms_dashboard_latency", true);
const status2xx = new Counter("http_status_2xx");
const status3xx = new Counter("http_status_3xx");
const status4xx = new Counter("http_status_4xx");
const status5xx = new Counter("http_status_5xx");
const statusOther = new Counter("http_status_other");

const authenticatedReads = [
  ["dashboard_summary", "/api/v1/dashboard/summary/", true],
  ["transport_requests", "/api/v1/transport-requests/?page=1&page_size=20", false],
  ["fleet_live_vehicles", "/api/v1/fleet-live/vehicles/", false],
  ["notifications", "/api/v1/auth/notifications/?page=1&page_size=20", false],
];

if (testDeviceId) {
  authenticatedReads.push([
    "vehicle_latest_status",
    `/api/v1/vehicles/${encodeURIComponent(testDeviceId)}/latest-status/`,
    false,
  ]);
}

if (includeReports) {
  authenticatedReads.push([
    "transport_request_report",
    "/api/v1/reports/transport-requests/?page=1&page_size=15",
    true,
  ]);
}

function envNumber(name, fallback) {
  const parsed = Number(__ENV[name] || fallback);
  if (!Number.isFinite(parsed) || parsed <= 0) throw new Error(`${name} must be positive.`);
  return parsed;
}

export const options = {
  stages: [
    { duration: __ENV.STAGE_1_DURATION || "30s", target: envNumber("STAGE_1_VUS", 10) },
    { duration: __ENV.STAGE_2_DURATION || "60s", target: envNumber("STAGE_2_VUS", 25) },
    { duration: __ENV.STAGE_3_DURATION || "60s", target: envNumber("STAGE_3_VUS", 50) },
    { duration: __ENV.STAGE_4_DURATION || "60s", target: envNumber("STAGE_4_VUS", 100) },
    { duration: __ENV.RAMP_DOWN_DURATION || "30s", target: 0 },
  ],
  thresholds: {
    ftms_read_errors: ["rate<0.01"],
    ftms_read_latency: ["p(95)<2000"],
    ftms_dashboard_latency: ["p(95)<3000"],
  },
  summaryTrendStats: ["avg", "min", "med", "p(90)", "p(95)", "p(99)", "max"],
};

function record(response, isDashboard = false) {
  const successful = response.status >= 200 && response.status < 300;
  requestErrors.add(!successful);
  requestSuccess.add(successful);
  if (isDashboard) dashboardLatency.add(response.timings.duration);
  else readLatency.add(response.timings.duration);
  if (response.status >= 200 && response.status < 300) status2xx.add(1);
  else if (response.status >= 300 && response.status < 400) status3xx.add(1);
  else if (response.status >= 400 && response.status < 500) status4xx.add(1);
  else if (response.status >= 500) status5xx.add(1);
  else statusOther.add(1);
  return successful;
}

export function setup() {
  if (!username || !password) fail("TEST_USERNAME and TEST_PASSWORD are required.");

  const csrf = http.get(`${baseUrl}/api/v1/auth/csrf/`, {
    tags: { endpoint: "csrf_setup" },
  });
  if (!check(csrf, { "CSRF bootstrap succeeded": (response) => response.status === 200 })) {
    fail(`CSRF bootstrap failed with HTTP ${csrf.status}.`);
  }

  const csrfToken = csrf.json("csrf_token");
  const login = http.post(
    `${baseUrl}/api/v1/auth/login/`,
    JSON.stringify({ username, password }),
    {
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      tags: { endpoint: "login_setup" },
    },
  );
  if (login.status !== 200) fail(`Staff login failed with HTTP ${login.status}.`);
  if (login.json("two_factor_required") === true) {
    fail("The load-test account has 2FA enabled. Use a dedicated eligible staging account without 2FA.");
  }
  const sessionCookie = login.cookies[sessionCookieName]?.[0]?.value;
  if (!sessionCookie) fail(`Login did not return the ${sessionCookieName} session cookie.`);

  return { sessionCookie };
}

export default function (data) {
  const headers = { Cookie: `${sessionCookieName}=${data.sessionCookie}` };
  const responses = http.batch([
    ["GET", `${baseUrl}/api/health/`, null, { tags: { endpoint: "health" } }],
    ...authenticatedReads.map(([name, path]) => [
      "GET", `${baseUrl}${path}`, null, { headers, tags: { endpoint: name } },
    ]),
  ]);

  responses.forEach((response, index) => {
    const name = index === 0 ? "health" : authenticatedReads[index - 1][0];
    const isDashboard = index > 0 && authenticatedReads[index - 1][2];
    check(response, { [`${name} returned HTTP 2xx`]: () => record(response, isDashboard) });
  });
  sleep(thinkTimeSeconds);
}

export function handleSummary(data) {
  const output = JSON.stringify(data, null, 2);
  const summaryPath = __ENV.SUMMARY_PATH || "load-test-summary.json";
  return { stdout: output, [summaryPath]: output };
}
