import { describe, expect, test } from "vitest";
import { roleLabel, type Role } from "./auth";

describe("roleLabel", () => {
  test.each<[Role, string]>([
    ["FLEET_ADMIN", "Fleet Admin"],
    ["FLEET_MANAGER", "Fleet Manager"],
    ["DISPATCHER", "Dispatcher"],
  ])("displays %s as %s without changing its API value", (role, label) => {
    expect(roleLabel(role)).toBe(label);
  });

  test("uses the neutral fallback when no role is available", () => {
    expect(roleLabel(undefined)).toBe("User");
  });
});
