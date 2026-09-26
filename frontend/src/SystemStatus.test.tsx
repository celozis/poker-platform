import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import SystemStatus from "./SystemStatus";

function stubFetch(result: Response | Error) {
  const fetch =
    result instanceof Error
      ? vi.fn().mockRejectedValue(result)
      : vi.fn().mockResolvedValue(result);
  vi.stubGlobal("fetch", fetch);
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("system status", () => {
  it("shows that the API and the database are available", async () => {
    stubFetch(jsonResponse({ api: "ok", database: "ok" }));

    render(<SystemStatus />);

    expect(await screen.findByText("API работает")).toBeInTheDocument();
    expect(screen.getByText("База данных доступна")).toBeInTheDocument();
  });

  it("shows that the database is unavailable when the API reports so", async () => {
    stubFetch(jsonResponse({ api: "ok", database: "unavailable" }));

    render(<SystemStatus />);

    expect(await screen.findByText("API работает")).toBeInTheDocument();
    expect(screen.getByText("База данных недоступна")).toBeInTheDocument();
  });

  it("shows that the API is unavailable when the request fails", async () => {
    stubFetch(new TypeError("Failed to fetch"));

    render(<SystemStatus />);

    expect(await screen.findByText("API недоступен")).toBeInTheDocument();
  });

  it("shows that the API is unavailable when it responds with an error", async () => {
    stubFetch(new Response("Bad Gateway", { status: 502 }));

    render(<SystemStatus />);

    expect(await screen.findByText("API недоступен")).toBeInTheDocument();
  });
});
