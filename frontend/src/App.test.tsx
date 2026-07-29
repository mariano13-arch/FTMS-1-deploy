import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";

afterEach(() => vi.restoreAllMocks());

test("shows loading and then connected when the backend is healthy", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(
      JSON.stringify({ status: "ok", service: "ftms-backend", database: "ok" }),
      { status: 200 },
    ),
  );

  render(<App />);

  expect(screen.getByRole("status")).toHaveTextContent("Loading");
  expect(await screen.findByText(/Backend connection: Connected/)).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "http://localhost:8000/api/health/",
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
});
