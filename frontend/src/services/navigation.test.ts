import { describe, expect, test } from "vitest";
import { safeInternalPath } from "./navigation";

describe("safe login redirects", () => {
  test("preserves an internal requested route", () => {
    expect(safeInternalPath("/vehicles/LILYGO-001")).toBe("/vehicles/LILYGO-001");
  });
  test.each([
    "https://evil.example", "//evil.example/path", "\\\\evil.example",
    "javascript:alert(1)", null, 42,
  ])("rejects external or protocol-relative value %s", (value) => {
    expect(safeInternalPath(value)).toBe("/transport-requests");
  });
});
