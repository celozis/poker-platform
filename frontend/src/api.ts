// Types mirror the response models in backend/app/schemas.py.
export type Club = {
  id: number;
  name: string;
  logo_url: string;
  primary_color: string;
  accent_color: string;
};

export type Admin = { id: number; name: string; phone: string };

export type Me = { admin: Admin; club: Club };

export type BlindLevel = {
  kind: "level";
  small_blind: number;
  big_blind: number;
  ante: number;
  duration_minutes: number;
};

export type Break = { kind: "break"; duration_minutes: number };

export type StructureItem = BlindLevel | Break;

export type BlindTemplate = { id: string; name: string; structure: StructureItem[] };

/** What the admin fills in; the rule levels count play levels only, null means not offered. */
export type TournamentInput = {
  name: string;
  starts_at: string;
  buy_in: number;
  starting_stack: number;
  structure: StructureItem[];
  reentry_until_level: number | null;
  addon_at_level: number | null;
  late_registration_until_level: number | null;
};

export type Tournament = TournamentInput & { id: number; status: "scheduled" | "cancelled" };

export type TournamentList = { upcoming: Tournament[]; past: Tournament[] };

/** A league player on the club's list. */
export type Player = { id: number; name: string; phone: string };

/** `consent`: the player agreed to the processing of personal data (152-ФЗ). */
export type PlayerInput = { name: string; phone: string; consent: boolean };

/** created: new in the league; added_to_club: known in the league, now also in this club. */
export type PlayerAdded = {
  player: Player;
  outcome: "created" | "added_to_club" | "already_in_club";
};

export type Registration = { player: Player; status: "registered" | "checked_in" };

export type TournamentRegistrations = {
  /** Players can sign up or drop out: the tournament is upcoming and not cancelled. */
  registration_open: boolean;
  /** Arrivals can be checked in: from 12 hours before the start to 12 hours after it. */
  check_in_open: boolean;
  registrations: Registration[];
};

function sendJson(
  method: "POST" | "PUT" | "DELETE",
  url: string,
  body?: unknown,
): Promise<Response> {
  return fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function postJson(url: string, body?: unknown): Promise<Response> {
  return sendJson("POST", url, body);
}

function failed(response: Response): Error {
  return new Error(`${response.url} failed with status ${response.status}`);
}

/** The logged-in admin, or null when nobody is logged in. */
export async function fetchMe(): Promise<Me | null> {
  const response = await fetch("/api/auth/me");
  if (response.status === 401) return null;
  if (!response.ok) throw failed(response);
  return response.json();
}

export async function requestCode(phone: string): Promise<void> {
  const response = await postJson("/api/auth/request-code", { phone });
  if (!response.ok) throw failed(response);
}

/** Returns false when the code is wrong or expired. */
export async function verifyCode(phone: string, code: string): Promise<boolean> {
  const response = await postJson("/api/auth/verify-code", { phone, code });
  if (response.status === 401) return false;
  if (!response.ok) throw failed(response);
  return true;
}

export async function logout(): Promise<void> {
  const response = await postJson("/api/auth/logout");
  if (!response.ok) throw failed(response);
}

function clubTournamentsUrl(clubId: number): string {
  return `/api/clubs/${clubId}/tournaments`;
}

export async function fetchTournaments(clubId: number): Promise<TournamentList> {
  const response = await fetch(clubTournamentsUrl(clubId));
  if (!response.ok) throw failed(response);
  return response.json();
}

export async function fetchBlindTemplates(): Promise<BlindTemplate[]> {
  const response = await fetch("/api/blind-templates");
  if (!response.ok) throw failed(response);
  return response.json();
}

/** The server refused: the data breaks a rule (422) or the action is not allowed now (409). */
export class RejectedError extends Error {
  messages: string[];

  constructor(messages: string[]) {
    super(messages.join("; "));
    this.messages = messages;
  }
}

async function throwIfRejected(response: Response): Promise<void> {
  if (response.status === 422 || response.status === 409) {
    const { detail } = await response.json();
    throw new RejectedError(Array.isArray(detail) ? detail : [detail]);
  }
  if (!response.ok) throw failed(response);
}

async function accepted<T>(response: Response): Promise<T> {
  await throwIfRejected(response);
  return response.json();
}

export async function createTournament(
  clubId: number,
  tournament: TournamentInput,
): Promise<Tournament> {
  return accepted(await sendJson("POST", clubTournamentsUrl(clubId), tournament));
}

export async function updateTournament(
  clubId: number,
  tournamentId: number,
  tournament: TournamentInput,
): Promise<Tournament> {
  const url = `${clubTournamentsUrl(clubId)}/${tournamentId}`;
  return accepted(await sendJson("PUT", url, tournament));
}

export async function cancelTournament(clubId: number, tournamentId: number): Promise<Tournament> {
  const url = `${clubTournamentsUrl(clubId)}/${tournamentId}/cancel`;
  return accepted(await postJson(url));
}

function clubPlayersUrl(clubId: number): string {
  return `/api/clubs/${clubId}/players`;
}

/** The club's players in name order; `query` narrows them down by name or phone. */
export async function fetchPlayers(clubId: number, query = ""): Promise<Player[]> {
  const search = query.trim() ? `?${new URLSearchParams({ q: query.trim() })}` : "";
  const response = await fetch(`${clubPlayersUrl(clubId)}${search}`);
  if (!response.ok) throw failed(response);
  return response.json();
}

export async function addPlayer(clubId: number, player: PlayerInput): Promise<PlayerAdded> {
  return accepted(await postJson(clubPlayersUrl(clubId), player));
}

function registrationsUrl(clubId: number, tournamentId: number): string {
  return `${clubTournamentsUrl(clubId)}/${tournamentId}/registrations`;
}

export async function fetchRegistrations(
  clubId: number,
  tournamentId: number,
): Promise<TournamentRegistrations> {
  const response = await fetch(registrationsUrl(clubId, tournamentId));
  if (!response.ok) throw failed(response);
  return response.json();
}

export async function registerPlayer(
  clubId: number,
  tournamentId: number,
  playerId: number,
): Promise<Registration> {
  const url = registrationsUrl(clubId, tournamentId);
  return accepted(await postJson(url, { player_id: playerId }));
}

export async function cancelRegistration(
  clubId: number,
  tournamentId: number,
  playerId: number,
): Promise<void> {
  const url = `${registrationsUrl(clubId, tournamentId)}/${playerId}`;
  await throwIfRejected(await sendJson("DELETE", url));
}

/** Marks the player as arrived (`arrived`), or takes a mistaken check-in back. */
export async function setCheckedIn(
  clubId: number,
  tournamentId: number,
  playerId: number,
  arrived: boolean,
): Promise<Registration> {
  const url = `${registrationsUrl(clubId, tournamentId)}/${playerId}/check-in`;
  return accepted(await sendJson(arrived ? "POST" : "DELETE", url));
}
