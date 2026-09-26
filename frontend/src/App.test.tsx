import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

const ME = {
  admin: { id: 1, name: "Анна Соколова", phone: "+79990000001" },
  club: {
    id: 7,
    name: "Покер-клуб «Обь»",
    logo_url: "/logos/ob.svg",
    primary_color: "#0B3D91",
    accent_color: "#F2A900",
  },
};
const VALID_CODE = "123456";

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// A stand-in for the backend auth API: remembers whether the browser is logged in.
function fakeBackend({ loggedIn = false, down = [] as string[] } = {}) {
  let session = loggedIn;
  const fetch = vi.fn(async (url: string, init?: RequestInit) => {
    const route = `${init?.method ?? "GET"} ${url}`;
    if (down.includes(route)) {
      throw new TypeError("Failed to fetch");
    }
    switch (route) {
      case "GET /api/health":
        return json({ api: "ok", database: "ok" });
      case "GET /api/auth/me":
        return session ? json(ME) : json({ detail: "Требуется вход" }, 401);
      case "POST /api/auth/request-code":
        return new Response(null, { status: 204 });
      case "POST /api/auth/verify-code": {
        const { code } = JSON.parse(String(init?.body));
        if (code !== VALID_CODE) {
          return json({ detail: "Неверный или просроченный код" }, 401);
        }
        session = true;
        return new Response(null, { status: 204 });
      }
      case "POST /api/auth/logout":
        session = false;
        return new Response(null, { status: 204 });
    }
    return json({ detail: "Not Found" }, 404);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("admin login", () => {
  it("shows the login form with the league branding to a visitor", async () => {
    fakeBackend();

    render(<App />);

    expect(await screen.findByLabelText("Номер телефона")).toBeInTheDocument();
    expect(screen.getByText("Сибирская лига покера")).toBeInTheDocument();
  });

  it("logs the admin in with the code and opens the panel in the club's branding", async () => {
    fakeBackend();
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("Номер телефона"), "+79990000001");
    await user.click(screen.getByRole("button", { name: "Получить код" }));
    await user.type(await screen.findByLabelText("Код из SMS"), VALID_CODE);
    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(
      await screen.findByRole("heading", { name: "Покер-клуб «Обь»" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Логотип: Покер-клуб «Обь»" })).toHaveAttribute(
      "src",
      "/logos/ob.svg",
    );
    expect(screen.getByRole("banner")).toHaveStyle({ backgroundColor: "#0B3D91" });
    expect(screen.getByText("Сибирская лига покера")).toBeInTheDocument();
    expect(screen.getByText("Анна Соколова")).toBeInTheDocument();
  });

  it("keeps the admin out and says why when the code is wrong", async () => {
    fakeBackend();
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("Номер телефона"), "+79990000001");
    await user.click(screen.getByRole("button", { name: "Получить код" }));
    await user.type(await screen.findByLabelText("Код из SMS"), "000000");
    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Неверный или просроченный код",
    );
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
  });

  it("lets the admin go back from the code step to fix the phone number", async () => {
    fakeBackend();
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("Номер телефона"), "+79990000009");
    await user.click(screen.getByRole("button", { name: "Получить код" }));
    await user.click(await screen.findByRole("button", { name: "Изменить номер" }));

    expect(screen.getByLabelText("Номер телефона")).toHaveValue("+79990000009");
  });

  it("tells the admin when the server cannot be reached", async () => {
    fakeBackend({ down: ["POST /api/auth/request-code"] });
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("Номер телефона"), "+79990000001");
    await user.click(screen.getByRole("button", { name: "Получить код" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Не удалось связаться с сервером",
    );
  });

  it("logs the admin out back to the login form", async () => {
    const fetch = fakeBackend({ loggedIn: true });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Выйти" }));

    expect(await screen.findByLabelText("Номер телефона")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/auth/logout", expect.objectContaining({ method: "POST" }));
  });
});
