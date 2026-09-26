// Mirrors ClubOut/AdminOut in backend/app/schemas.py and Me in backend/app/auth.py.
export type Club = {
  id: number;
  name: string;
  logo_url: string;
  primary_color: string;
  accent_color: string;
};

export type Admin = { id: number; name: string; phone: string };

export type Me = { admin: Admin; club: Club };

function postJson(url: string, body?: unknown): Promise<Response> {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
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
