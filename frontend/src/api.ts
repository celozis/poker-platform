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
  /** Chips an add-on gives; needed only when the add-on is offered. */
  addon_stack: number | null;
  /** What an add-on costs, in roubles; needed only when the add-on is offered. A re-entry costs
   * the buy-in. */
  addon_price: number | null;
  late_registration_until_level: number | null;
  seats_per_table: number;
};

/** scheduled → running ⇄ paused → finished; or scheduled → cancelled. */
export type TournamentStatus = "scheduled" | "running" | "paused" | "finished" | "cancelled";

/** `board_token`: the secret part of the hall board's link, /board/<board_token>. */
export type Tournament = TournamentInput & {
  id: number;
  status: TournamentStatus;
  board_token: string;
};

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

/** `refunded`: roubles given back by a storno of the buy-in the player paid; 0 when none. */
export type Refund = { refunded: number };

/** Takes the player off the tournament before the start, giving back a buy-in they paid. */
export async function cancelRegistration(
  clubId: number,
  tournamentId: number,
  playerId: number,
): Promise<Refund> {
  const url = `${registrationsUrl(clubId, tournamentId)}/${playerId}`;
  return accepted(await sendJson("DELETE", url));
}

/** How a player pays: every payment is a transaction in the tournament's cashier. */
export type PaymentMethod = "cash" | "card";

/** What a paid action sends: nothing when there is nothing to pay. */
function payment(method: PaymentMethod | null): { payment_method: PaymentMethod } | undefined {
  return method === null ? undefined : { payment_method: method };
}

function checkInUrl(clubId: number, tournamentId: number, playerId: number): string {
  return `${registrationsUrl(clubId, tournamentId)}/${playerId}/check-in`;
}

/** Marks the player as arrived; they pay the buy-in (`method`, null when the tournament is free). */
export async function checkIn(
  clubId: number,
  tournamentId: number,
  playerId: number,
  method: PaymentMethod | null,
): Promise<Registration> {
  return accepted(await sendJson("POST", checkInUrl(clubId, tournamentId, playerId), payment(method)));
}

/** Takes a mistaken check-in back, and the buy-in with it. */
export async function undoCheckIn(
  clubId: number,
  tournamentId: number,
  playerId: number,
): Promise<Registration & Refund> {
  return accepted(await sendJson("DELETE", checkInUrl(clubId, tournamentId, playerId)));
}

export type Clock = {
  running: boolean;
  /** The structure item (level or break) being played: an index into the tournament's structure. */
  item: number;
  /** To the millisecond, so that every screen's countdown turns over together. */
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

/** `points`: rating points, once the tournament is finished. */
export type FinishedPlayer = {
  player: Player;
  place: number;
  reentries: number;
  addons: number;
  points: number | null;
};

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

/** A re-entry, an add-on and a late seat are paid for (`method`, null when free). */
export async function actOnPlayer(
  clubId: number,
  tournamentId: number,
  playerId: number,
  action: PlayerAction,
  method: PaymentMethod | null = null,
): Promise<GameState> {
  const url = `${tournamentUrl(clubId, tournamentId)}/players/${playerId}/${action}`;
  return accepted(await postJson(url, payment(method)));
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

/** A tournament as the hall board shows it to everyone in the club: no player names. */
export type BoardState = {
  club: Club;
  name: string;
  starts_at: string;
  status: TournamentStatus;
  starting_stack: number;
  structure: StructureItem[];
  /** null until the tournament starts. */
  clock: Clock | null;
  /** Still at the tables. */
  players_left: number;
  /** Everyone who has sat down at a table, counted once however many times they re-entered. */
  players: number;
  reentries: number;
  /** null while nobody is at a table. */
  average_stack: number | null;
};

/** The hall board, opened by its secret link without login; null when there is no such board. */
export async function fetchBoard(token: string): Promise<BoardState | null> {
  const response = await fetch(`/api/board/${token}`);
  if (response.status === 404) return null;
  if (!response.ok) throw failed(response);
  return response.json();
}

/** Where the hall board hears of every change: the board on connecting, then after each change. */
export function boardSocketUrl(token: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/api/board/${token}/ws`;
}

/** A player's result in a finished tournament. */
export type TournamentResult = {
  place: number;
  player: Player;
  points: number;
  reentries: number;
  addons: number;
};

/** `results`: by place, the winner first; empty until the tournament is finished. */
export type TournamentResults = { status: TournamentStatus; results: TournamentResult[] };

export async function fetchResults(clubId: number, tournamentId: number): Promise<TournamentResults> {
  const response = await fetch(`${tournamentUrl(clubId, tournamentId)}/results`);
  if (!response.ok) throw failed(response);
  return response.json();
}

/** Puts the player on the place they really finished in; everyone's points are counted again. */
export async function correctPlace(
  clubId: number,
  tournamentId: number,
  playerId: number,
  place: number,
): Promise<TournamentResults> {
  const url = `${tournamentUrl(clubId, tournamentId)}/results/${playerId}`;
  return accepted(await sendJson("PUT", url, { place }));
}

/** A rating season: a half of the year. `id` such as "2026-2"; days as "2026-07-01". */
export type Season = { id: string; name: string; first_day: string; last_day: string };

/** Equal points share a position. `tournaments`: finished ones played this season. */
export type RatingRow = { position: number; player: Player; points: number; tournaments: number };

/** `next_season` is null for the current season: the rating looks back, not ahead. */
export type ClubRating = {
  season: Season;
  previous_season: string;
  next_season: string | null;
  players: RatingRow[];
};

/** The club rating of the current season, or of an earlier one by its id. */
export async function fetchRating(clubId: number, season?: string): Promise<ClubRating> {
  const query = season ? `?${new URLSearchParams({ season })}` : "";
  const response = await fetch(`/api/clubs/${clubId}/rating${query}`);
  if (!response.ok) throw failed(response);
  return response.json();
}

export type TransactionKind = "buy_in" | "reentry" | "addon";

/** A payment of a tournament. `amount` in roubles, negative for a storno; `reverses_id`: the
 * operation a storno reverses; `replaces_id`: the payment taken the wrong way that this one
 * replaces; `reversed_by_id`: the storno that has reversed this one. */
export type Transaction = {
  id: number;
  created_at: string;
  kind: TransactionKind;
  amount: number;
  payment_method: PaymentMethod;
  player: Player;
  /** Who took the money, or reversed it. */
  admin: Admin;
  reverses_id: number | null;
  replaces_id: number | null;
  reversed_by_id: number | null;
};

/** `count`: operations that stand, neither a storno nor reversed. */
export type KindTotal = { kind: TransactionKind; count: number; amount: number };

export type MethodTotal = { payment_method: PaymentMethod; amount: number };

/** A tournament's cashier: always all three kinds and both methods; operations in the order
 * they were made. */
export type Cashier = {
  by_kind: KindTotal[];
  by_method: MethodTotal[];
  total: number;
  transactions: Transaction[];
};

function cashierUrl(clubId: number, tournamentId: number): string {
  return `${tournamentUrl(clubId, tournamentId)}/cashier`;
}

export async function fetchCashier(clubId: number, tournamentId: number): Promise<Cashier> {
  const response = await fetch(cashierUrl(clubId, tournamentId));
  if (!response.ok) throw failed(response);
  return response.json();
}

/** Where the browser downloads the cashier as a CSV file for Excel. */
export function cashierCsvUrl(clubId: number, tournamentId: number): string {
  return `${cashierUrl(clubId, tournamentId)}.csv`;
}

/** Reverses a mistaken operation by a storno; the operation stays in the history. */
export async function reverseTransaction(
  clubId: number,
  tournamentId: number,
  transactionId: number,
): Promise<Cashier> {
  const url = `${cashierUrl(clubId, tournamentId)}/transactions/${transactionId}/reverse`;
  return accepted(await postJson(url));
}

/** Puts right a payment taken the wrong way: a storno, and the same payment taken `method`. */
export async function changePaymentMethod(
  clubId: number,
  tournamentId: number,
  transactionId: number,
  method: PaymentMethod,
): Promise<Cashier> {
  const url = `${cashierUrl(clubId, tournamentId)}/transactions/${transactionId}/payment-method`;
  return accepted(await postJson(url, { payment_method: method }));
}
