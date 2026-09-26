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

function sendJson(method: "POST" | "PUT", url: string, body?: unknown): Promise<Response> {
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

/** The server refused to save: the data breaks a rule (422) or the tournament is locked (409). */
export class RejectedError extends Error {
  messages: string[];

  constructor(messages: string[]) {
    super(messages.join("; "));
    this.messages = messages;
  }
}

async function savedTournament(response: Response): Promise<Tournament> {
  if (response.status === 422 || response.status === 409) {
    const { detail } = await response.json();
    throw new RejectedError(Array.isArray(detail) ? detail : [detail]);
  }
  if (!response.ok) throw failed(response);
  return response.json();
}

export async function createTournament(
  clubId: number,
  tournament: TournamentInput,
): Promise<Tournament> {
  return savedTournament(await sendJson("POST", clubTournamentsUrl(clubId), tournament));
}

export async function updateTournament(
  clubId: number,
  tournamentId: number,
  tournament: TournamentInput,
): Promise<Tournament> {
  const url = `${clubTournamentsUrl(clubId)}/${tournamentId}`;
  return savedTournament(await sendJson("PUT", url, tournament));
}

export async function cancelTournament(clubId: number, tournamentId: number): Promise<Tournament> {
  const url = `${clubTournamentsUrl(clubId)}/${tournamentId}/cancel`;
  return savedTournament(await postJson(url));
}
