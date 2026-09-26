import { vi } from "vitest";
import type {
  BlindTemplate,
  Player,
  Registration,
  Tournament,
  TournamentList,
} from "../api";

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

export function aPlayer(overrides: Partial<Player> = {}): Player {
  return { id: 1, name: "Иван Петров", phone: "+79135551234", ...overrides };
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
  /** The club's own players. */
  players?: Player[];
  /** Players known in the league but not yet in the club. */
  leaguePlayers?: Player[];
  /** Registrations by tournament id. */
  registrations?: Record<number, Registration[]>;
  registrationOpen?: boolean;
  checkInOpen?: boolean;
};

const CONSENT_MISSING = "Без согласия на обработку персональных данных игрока завести нельзя";

function normalizePhone(raw: string): string | null {
  const digits = raw.replace(/\D/g, "");
  return digits.length === 11 && "78".includes(digits[0]) ? `+7${digits.slice(1)}` : null;
}

function matches(player: Player, query: string): boolean {
  const digits = query.replace(/\D/g, "");
  return (
    player.name.toLowerCase().includes(query.toLowerCase()) ||
    (digits !== "" && player.phone.includes(digits))
  );
}

const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name, "ru");

// A stand-in for the backend API: remembers whether the browser is logged in and the club's tournaments.
export function fakeBackend({
  loggedIn = false,
  down = [],
  tournaments = { upcoming: [], past: [] },
  rejectWith,
  players = [],
  leaguePlayers = [],
  registrations = {},
  registrationOpen = true,
  checkInOpen = true,
}: FakeBackendOptions = {}) {
  let session = loggedIn;
  const state: TournamentList = structuredClone(tournaments);
  const clubPlayers: Player[] = structuredClone(players);
  const league: Player[] = structuredClone(leaguePlayers);
  const signedUp: Record<number, Registration[]> = structuredClone(registrations);
  let nextId = 100;
  const clubTournaments = `/api/clubs/${ME.club.id}/tournaments`;
  const clubPlayersUrl = `/api/clubs/${ME.club.id}/players`;

  function addPlayer(body: { name: string; phone: string; consent: boolean }) {
    const phone = normalizePhone(body.phone);
    const errors = [
      ...(body.name.trim() ? [] : ["Укажите имя игрока"]),
      ...(phone ? [] : ["Телефон: нужен российский номер из 11 цифр, например +7 913 555-12-34"]),
      ...(body.consent ? [] : [CONSENT_MISSING]),
    ];
    if (errors.length > 0) return json({ detail: errors }, 422);
    const inClub = clubPlayers.find((p) => p.phone === phone);
    if (inClub) return json({ player: inClub, outcome: "already_in_club" });
    const known = league.find((p) => p.phone === phone);
    if (known) {
      clubPlayers.push(known);
      return json({ player: known, outcome: "added_to_club" });
    }
    const created: Player = { id: nextId++, name: body.name.trim(), phone: phone! };
    clubPlayers.push(created);
    return json({ player: created, outcome: "created" }, 201);
  }

  function registrationsRoute(method: string, tournamentId: number, rest: string, body: { player_id: number }) {
    const list = (signedUp[tournamentId] ??= []);
    if (rest === "" && method === "GET") {
      return json({
        registration_open: registrationOpen,
        check_in_open: checkInOpen,
        registrations: [...list].sort((a, b) => byName(a.player, b.player)),
      });
    }
    if (rest === "" && method === "POST") {
      const player = clubPlayers.find((p) => p.id === body.player_id);
      if (!player) return json({ detail: "Игрок не найден в клубе" }, 404);
      if (list.some((r) => r.player.id === player.id)) {
        return json({ detail: `${player.name} уже зарегистрирован на этот турнир` }, 409);
      }
      const registration: Registration = { player, status: "registered" };
      list.push(registration);
      return json(registration, 201);
    }
    const [, playerId, checkIn] = rest.match(/^\/(\d+)(\/check-in)?$/) ?? [];
    const registration = list.find((r) => r.player.id === Number(playerId));
    if (!registration) return json({ detail: "Игрок не зарегистрирован на этот турнир" }, 404);
    if (checkIn) {
      registration.status = method === "POST" ? "checked_in" : "registered";
      return json(registration);
    }
    signedUp[tournamentId] = list.filter((r) => r !== registration);
    return new Response(null, { status: 204 });
  }

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
      case `POST ${clubPlayersUrl}`:
        return addPlayer(body);
      case `POST ${clubTournaments}`: {
        if (rejectWith) return json({ detail: rejectWith }, 422);
        const created: Tournament = { ...body, id: nextId++, status: "scheduled" };
        state.upcoming.push(created);
        return json(created, 201);
      }
    }
    const { pathname, searchParams } = new URL(url, "http://localhost");
    if (method === "GET" && pathname === clubPlayersUrl) {
      const query = (searchParams.get("q") ?? "").trim();
      return json(clubPlayers.filter((p) => !query || matches(p, query)).sort(byName));
    }
    const registrationsMatch = url.match(/^\/api\/clubs\/\d+\/tournaments\/(\d+)\/registrations(.*)$/);
    if (registrationsMatch) {
      return registrationsRoute(method, Number(registrationsMatch[1]), registrationsMatch[2], body);
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
