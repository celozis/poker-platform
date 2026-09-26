import { vi } from "vitest";
import type { BlindTemplate, Tournament, TournamentList } from "../api";

export const ME = {
  admin: { id: 1, name: "Анна Соколова", phone: "+79990000001" },
  club: {
    id: 7,
    name: "Покер-клуб «Обь»",
    logo_url: "/logos/ob.svg",
    primary_color: "#0B3D91",
    accent_color: "#F2A900",
  },
};
export const VALID_CODE = "123456";

export const TEMPLATES: BlindTemplate[] = [
  {
    id: "standard",
    name: "Стандартная лиги",
    structure: [
      { kind: "level", small_blind: 100, big_blind: 200, ante: 0, duration_minutes: 20 },
      { kind: "level", small_blind: 200, big_blind: 400, ante: 0, duration_minutes: 20 },
      { kind: "break", duration_minutes: 10 },
      { kind: "level", small_blind: 300, big_blind: 600, ante: 75, duration_minutes: 20 },
    ],
  },
  {
    id: "turbo",
    name: "Турбо",
    structure: [
      { kind: "level", small_blind: 100, big_blind: 200, ante: 0, duration_minutes: 10 },
      { kind: "level", small_blind: 200, big_blind: 400, ante: 0, duration_minutes: 10 },
    ],
  },
];

/** A tournament of ME's club as the backend returns it; override any field. */
export function aTournament(overrides: Partial<Tournament> = {}): Tournament {
  return {
    id: 1,
    name: "Пятничный турнир",
    starts_at: "2026-10-02T12:00:00Z",
    buy_in: 2000,
    starting_stack: 20000,
    structure: TEMPLATES[0].structure,
    reentry_until_level: 2,
    addon_at_level: 2,
    late_registration_until_level: 3,
    status: "scheduled",
    ...overrides,
  };
}

export function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type FakeBackendOptions = {
  loggedIn?: boolean;
  /** Routes such as "POST /api/auth/request-code" that fail as if the server were unreachable. */
  down?: string[];
  tournaments?: TournamentList;
  /** Messages a 422 answer carries when a tournament is created or edited. */
  rejectWith?: string[];
};

// A stand-in for the backend API: remembers whether the browser is logged in and the club's tournaments.
export function fakeBackend({
  loggedIn = false,
  down = [],
  tournaments = { upcoming: [], past: [] },
  rejectWith,
}: FakeBackendOptions = {}) {
  let session = loggedIn;
  const state: TournamentList = structuredClone(tournaments);
  let nextId = 100;
  const clubTournaments = `/api/clubs/${ME.club.id}/tournaments`;

  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    const route = `${method} ${url}`;
    if (down.includes(route)) {
      throw new TypeError("Failed to fetch");
    }
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    switch (route) {
      case "GET /api/health":
        return json({ api: "ok", database: "ok" });
      case "GET /api/auth/me":
        return session ? json(ME) : json({ detail: "Требуется вход" }, 401);
      case "POST /api/auth/request-code":
        return new Response(null, { status: 204 });
      case "POST /api/auth/verify-code": {
        if (body.code !== VALID_CODE) {
          return json({ detail: "Неверный или просроченный код" }, 401);
        }
        session = true;
        return new Response(null, { status: 204 });
      }
      case "POST /api/auth/logout":
        session = false;
        return new Response(null, { status: 204 });
      case "GET /api/blind-templates":
        return json(TEMPLATES);
      case `GET ${clubTournaments}`:
        return json(state);
      case `POST ${clubTournaments}`: {
        if (rejectWith) return json({ detail: rejectWith }, 422);
        const created: Tournament = { ...body, id: nextId++, status: "scheduled" };
        state.upcoming.push(created);
        return json(created, 201);
      }
    }
    const [, id, action] = url.match(/^\/api\/clubs\/\d+\/tournaments\/(\d+)(\/cancel)?$/) ?? [];
    const tournament = state.upcoming.find((t) => t.id === Number(id));
    if (tournament && method === "PUT" && !action) {
      if (rejectWith) return json({ detail: rejectWith }, 422);
      Object.assign(tournament, body);
      return json(tournament);
    }
    if (tournament && method === "POST" && action) {
      tournament.status = "cancelled";
      return json(tournament);
    }
    return json({ detail: "Not Found" }, 404);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
