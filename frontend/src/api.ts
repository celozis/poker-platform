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
  seats_per_table: number;
};

/** scheduled → running ⇄ paused → finished; or scheduled → cancelled. */
export type TournamentStatus = "scheduled" | "running" | "paused" | "finished" | "cancelled";

export type Tournament = TournamentInput & { id: number; status: TournamentStatus };

/** live: running or paused; upcoming: not started yet, however late. */
export type TournamentList = { live: Tournament[]; upcoming: Tournament[]; past: Tournament[] };

/** A league player on the club's list. */
export type Player = { id: number; name: string; phone: string };

/** `consent`: the player agreed to the processing of personal data (152-ФЗ). */
export type PlayerInput = { name: string; phone: string; consent: boolean };

/** created: new in the league; added_to_club: known in the league, now also in this club. */
export type PlayerAdded = {
  player: Player;
  outcome: "created" | "added_to_club" | "already_in_club";
};

export type Registration = {
  player: Player;
  status: "registered" | "checked_in" | "in_game" | "out";
};

export type TournamentRegistrations = {
  /** Players can sign up: until the tournament is started, then while late registration is open. */
  registration_open: boolean;
  /** Players can drop out: until the tournament is started. */
  drop_out_open: boolean;
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

function tournamentUrl(clubId: number, tournamentId: number): string {
  return `${clubTournamentsUrl(clubId)}/${tournamentId}`;
}

export async function updateTournament(
  clubId: number,
  tournamentId: number,
  tournament: TournamentInput,
): Promise<Tournament> {
  return accepted(await sendJson("PUT", tournamentUrl(clubId, tournamentId), tournament));
}

export async function cancelTournament(clubId: number, tournamentId: number): Promise<Tournament> {
  return accepted(await postJson(`${tournamentUrl(clubId, tournamentId)}/cancel`));
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
  return `${tournamentUrl(clubId, tournamentId)}/registrations`;
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

export type Clock = {
  running: boolean;
  /** The structure item (level or break) being played: an index into the tournament's structure. */
  item: number;
  seconds_left: number;
};

export type EntryWindows = { reentry: boolean; addon: boolean; late_registration: boolean };

export type SeatedPlayer = {
  player: Player;
  table: number;
  seat: number;
  reentries: number;
  addons: number;
  /** One add-on per entry: whether the current entry has had it. */
  addon_this_entry: boolean;
};

export type FinishedPlayer = { player: Player; place: number; reentries: number; addons: number };

export type Move = {
  player: Player;
  from_table: number;
  from_seat: number;
  to_table: number;
  to_seat: number;
};

/** A tournament's game as the admin runs it; every action answers with the whole of it. */
export type GameState = {
  status: TournamentStatus;
  seats_per_table: number;
  /** null until the tournament starts. */
  clock: Clock | null;
  windows: EntryWindows;
  /** By table and seat. */
  in_game: SeatedPlayer[];
  /** Knocked out, and at the end the winner; by place. */
  out: FinishedPlayer[];
  /** Registered but not seated. */
  waiting: Registration[];
  /** A move that keeps tables even, when they are not. */
  suggested_move: Move | null;
};

export async function fetchGame(clubId: number, tournamentId: number): Promise<GameState> {
  const response = await fetch(`${tournamentUrl(clubId, tournamentId)}/game`);
  if (!response.ok) throw failed(response);
  return response.json();
}

export type GameAction = "start" | "pause" | "resume" | "next-level" | "previous-level";

export async function runGame(
  clubId: number,
  tournamentId: number,
  action: GameAction,
): Promise<GameState> {
  return accepted(await postJson(`${tournamentUrl(clubId, tournamentId)}/${action}`));
}

/** undo-knock-out: a mistaken knock-out taken back; seat: a late player sits down. */
export type PlayerAction = "knock-out" | "undo-knock-out" | "reentry" | "addon" | "seat";

export async function actOnPlayer(
  clubId: number,
  tournamentId: number,
  playerId: number,
  action: PlayerAction,
): Promise<GameState> {
  const url = `${tournamentUrl(clubId, tournamentId)}/players/${playerId}/${action}`;
  return accepted(await postJson(url));
}

export async function movePlayer(
  clubId: number,
  tournamentId: number,
  playerId: number,
  to: { table: number; seat: number },
): Promise<GameState> {
  const url = `${tournamentUrl(clubId, tournamentId)}/players/${playerId}/move`;
  return accepted(await postJson(url, to));
}
