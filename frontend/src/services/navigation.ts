export function safeInternalPath(requested: unknown): string {
  if (
    typeof requested !== "string" ||
    !requested.startsWith("/") ||
    requested.startsWith("//") ||
    requested.includes("\\") ||
    /^[a-z][a-z0-9+.-]*:/i.test(requested)
  ) {
    return "/vehicles";
  }
  return requested;
}
