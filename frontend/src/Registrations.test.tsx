import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Player } from "./api";
import { aPlayer, aTournament, fakeBackend, ME } from "./testing/fakeBackend";
import { fakeWebSockets } from "./testing/fakeWebSocket";

afterEach(() => {
  vi.unstubAllGlobals();
});

const IVAN = aPlayer({ id: 1, name: "Иван Петров", phone: "+79135551234" });
const MARIA = aPlayer({ id: 2, name: "Мария Иванова", phone: "+79131110002" });
const FRIDAY = aTournament({ id: 5, name: "Пятничный турнир" });

async function openRegistrations(tournamentName = "Пятничный турнир") {
  const user = userEvent.setup();
  render(<App />);
  const row = await screen.findByRole("listitem", { name: tournamentName });
  await user.click(within(row).getByRole("button", { name: "Регистрации" }));
  await screen.findByRole("heading", { name: tournamentName });
  return user;
}

function registered() {
  return screen.getByRole("list", { name: "Зарегистрированные игроки" });
}

describe("tournament registrations", () => {
  it("registers a club player found by name", async () => {
    fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [FRIDAY], past: [] },
      players: [IVAN, MARIA],
    });
    const user = await openRegistrations();
    expect(await screen.findByText("Пока никто не зарегистрирован")).toBeInTheDocument();

    await user.type(screen.getByRole("searchbox", { name: "Найти игрока клуба" }), "Мария");
    const found = await screen.findByRole("list", { name: "Найденные игроки" });
    await user.click(
      within(within(found).getByRole("listitem", { name: "Мария Иванова" })).getByRole("button", {
        name: "Зарегистрировать",
      }),
    );

    const row = await within(await screen.findByRole("list", { name: "Зарегистрированные игроки" }))
      .findByRole("listitem", { name: "Мария Иванова" });
    expect(row).toHaveTextContent("Зарегистрирован");
    expect(screen.getByText("Зарегистрировано: 1, пришли: 0")).toBeInTheDocument();
    expect(
      within(within(found).getByRole("listitem", { name: "Мария Иванова" })).queryByRole("button"),
    ).not.toBeInTheDocument();
  });

  it("closes registration to players, still registers them itself, and opens it again", async () => {
    const fetch = fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [FRIDAY], past: [] },
      players: [IVAN, MARIA],
    });
    const user = await openRegistrations();

    await user.click(await screen.findByRole("button", { name: "Закрыть запись" }));

    expect(fetch).toHaveBeenCalledWith(
      "/api/clubs/7/tournaments/5/registrations/close",
      expect.objectContaining({ method: "POST" }),
    );
    expect(
      await screen.findByText("Запись закрыта: игроки не могут записаться сами, вы можете записать игрока."),
    ).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Найти игрока клуба" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Открыть запись" }));
    expect(await screen.findByRole("button", { name: "Закрыть запись" })).toBeInTheDocument();
  });

  it("offers no closing of registration once the tournament has started", async () => {
    fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [FRIDAY], past: [] },
      dropOutOpen: false,
    });
    await openRegistrations();

    await screen.findByText("Пока никто не зарегистрирован");
    expect(screen.queryByRole("button", { name: "Закрыть запись" })).not.toBeInTheDocument();
  });

  it("adds a new player and registers them in one go", async () => {
    fakeBackend({ loggedIn: true, tournaments: { upcoming: [FRIDAY], past: [] } });
    const user = await openRegistrations();

    await user.click(await screen.findByRole("button", { name: "Новый игрок" }));
    await user.type(screen.getByLabelText("Имя"), "Сергей Никитин");
    await user.type(screen.getByLabelText("Телефон"), "89131110003");
    await user.click(screen.getByLabelText(/Игрок согласен/));
    await user.click(screen.getByRole("button", { name: "Добавить и зарегистрировать" }));

    expect(
      await within(registered()).findByRole("listitem", { name: "Сергей Никитин" }),
    ).toHaveTextContent("+7 913 111-00-03");
  });

  it("says whose phone it is when a new player turns out to be known in the league", async () => {
    fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [FRIDAY], past: [] },
      leaguePlayers: [IVAN],
    });
    const user = await openRegistrations();

    await user.click(await screen.findByRole("button", { name: "Новый игрок" }));
    await user.type(screen.getByLabelText("Имя"), "Ваня");
    await user.type(screen.getByLabelText("Телефон"), "8 913 555-12-34");
    await user.click(screen.getByLabelText(/Игрок согласен/));
    await user.click(screen.getByRole("button", { name: "Добавить и зарегистрировать" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Игрок Иван Петров уже есть в лиге и теперь добавлен в ваш клуб",
    );
    expect(
      await within(registered()).findByRole("listitem", { name: "Иван Петров" }),
    ).toHaveTextContent("Зарегистрирован");
  });

  it("does not claim the player was not added when only the registration is refused", async () => {
    fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [FRIDAY], past: [] },
      players: [IVAN],
      registrations: { 5: [{ player: IVAN, status: "registered" }] },
    });
    const user = await openRegistrations();

    await user.click(await screen.findByRole("button", { name: "Новый игрок" }));
    await user.type(screen.getByLabelText("Имя"), "Иван Петров");
    await user.type(screen.getByLabelText("Телефон"), "+79135551234");
    await user.click(screen.getByLabelText(/Игрок согласен/));
    await user.click(screen.getByRole("button", { name: "Добавить и зарегистрировать" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Иван Петров уже зарегистрирован на этот турнир",
    );
    expect(screen.queryByText(/Игрок не добавлен/)).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Игрок Иван Петров уже есть в вашем клубе");
  });

  it("takes the buy-in on checking in an arrival and gives it back when the check-in is undone", async () => {
    const fetch = fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [FRIDAY], past: [] },
      players: [IVAN, MARIA],
      registrations: {
        5: [
          { player: IVAN, status: "registered" },
          { player: MARIA, status: "registered" },
        ],
      },
    });
    const user = await openRegistrations();
    const ivan = await within(registered()).findByRole("listitem", { name: "Иван Петров" });

    await user.click(within(ivan).getByRole("button", { name: "Отметить приход" }));
    const payment = screen.getByRole("dialog", { name: "Оплата" });
    expect(payment).toHaveTextContent("Бай-ин: Иван Петров");
    expect(payment).toHaveTextContent("2 000 ₽");
    await user.click(within(payment).getByRole("button", { name: "Карта" }));

    expect(await within(ivan).findByText("Пришёл")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText("Зарегистрировано: 2, пришли: 1")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/clubs/7/tournaments/5/registrations/1/check-in",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ payment_method: "card" }) }),
    );

    await user.click(within(ivan).getByRole("button", { name: "Отменить приход" }));
    expect(await within(ivan).findByText("Зарегистрирован")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Приход игрока Иван Петров отменён, бай-ин сторнирован: верните игроку 2 000 ₽",
    );
  });

  it("says what the server actually gave back, not today's buy-in", async () => {
    fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [FRIDAY], past: [] },
      players: [IVAN, MARIA],
      registrations: {
        5: [
          { player: IVAN, status: "checked_in" },
          { player: MARIA, status: "checked_in" },
        ],
      },
      // Paid before the buy-in went up to 2 000 ₽; Maria's was reversed in the cashier already.
      refunds: { 1: 1500, 2: 0 },
    });
    vi.stubGlobal("confirm", vi.fn(() => true));
    const user = await openRegistrations();
    const ivan = await within(registered()).findByRole("listitem", { name: "Иван Петров" });

    await user.click(within(ivan).getByRole("button", { name: "Отменить приход" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Приход игрока Иван Петров отменён, бай-ин сторнирован: верните игроку 1 500 ₽",
    );

    const maria = within(registered()).getByRole("listitem", { name: "Мария Иванова" });
    await user.click(within(maria).getByRole("button", { name: "Снять с регистрации" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Регистрация игрока Мария Иванова отменена");
    expect(screen.getByRole("status")).not.toHaveTextContent("верните");
  });

  it("does not check in a player whose payment was called off", async () => {
    const fetch = fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [FRIDAY], past: [] },
      players: [IVAN],
      registrations: { 5: [{ player: IVAN, status: "registered" }] },
    });
    const user = await openRegistrations();
    const ivan = await within(registered()).findByRole("listitem", { name: "Иван Петров" });

    await user.click(within(ivan).getByRole("button", { name: "Отметить приход" }));
    await user.click(
      within(screen.getByRole("dialog", { name: "Оплата" })).getByRole("button", { name: "Отмена" }),
    );

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(within(ivan).getByText("Зарегистрирован")).toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/check-in"))).toBe(false);
  });

  it("checks in to a free tournament without asking for money", async () => {
    fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [{ ...FRIDAY, buy_in: 0 }], past: [] },
      players: [IVAN],
      registrations: { 5: [{ player: IVAN, status: "registered" }] },
    });
    const user = await openRegistrations();
    const ivan = await within(registered()).findByRole("listitem", { name: "Иван Петров" });

    await user.click(within(ivan).getByRole("button", { name: "Отметить приход" }));

    expect(await within(ivan).findByText("Пришёл")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("gives the buy-in back to a player who came and then drops out", async () => {
    fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [FRIDAY], past: [] },
      players: [IVAN],
      registrations: { 5: [{ player: IVAN, status: "checked_in" }] },
    });
    const confirm = vi.fn(() => true);
    vi.stubGlobal("confirm", confirm);
    const user = await openRegistrations();
    const ivan = await within(registered()).findByRole("listitem", { name: "Иван Петров" });

    await user.click(within(ivan).getByRole("button", { name: "Снять с регистрации" }));

    expect(confirm).toHaveBeenCalledWith(
      "Снять Иван Петров с регистрации на турнир? Бай-ин будет сторнирован.",
    );
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Регистрация игрока Иван Петров отменена, бай-ин сторнирован: верните игроку 2 000 ₽",
    );
    expect(screen.getByText("Пока никто не зарегистрирован")).toBeInTheDocument();
  });

  it("cancels a registration after the admin confirms", async () => {
    fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [FRIDAY], past: [] },
      players: [IVAN, MARIA],
      registrations: {
        5: [
          { player: IVAN, status: "registered" },
          { player: MARIA, status: "registered" },
        ],
      },
    });
    const confirm = vi.fn(() => true);
    vi.stubGlobal("confirm", confirm);
    const user = await openRegistrations();
    const ivan = await within(registered()).findByRole("listitem", { name: "Иван Петров" });

    await user.click(within(ivan).getByRole("button", { name: "Снять с регистрации" }));

    expect(confirm).toHaveBeenCalledWith("Снять Иван Петров с регистрации на турнир?");
    await vi.waitFor(() =>
      expect(within(registered()).queryByRole("listitem", { name: "Иван Петров" })).toBeNull(),
    );
    expect(within(registered()).getByRole("listitem", { name: "Мария Иванова" })).toBeInTheDocument();
  });

  it("offers no sign-ups or check-ins once they are closed", async () => {
    const past = aTournament({ id: 6, name: "Летний кубок", starts_at: "2026-08-01T12:00:00Z" });
    fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [], past: [past] },
      players: [IVAN],
      registrations: { 6: [{ player: IVAN, status: "checked_in" }] },
      registrationOpen: false,
      checkInOpen: false,
    });
    await openRegistrations("Летний кубок");

    const ivan = await within(registered()).findByRole("listitem", { name: "Иван Петров" });
    expect(ivan).toHaveTextContent("Пришёл");
    expect(within(ivan).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
    expect(screen.getByText(/Регистрация закрыта/)).toBeInTheDocument();
  });

  it("shows who plays and who is out once the tournament is running", async () => {
    const live = aTournament({ id: 7, name: "Субботний турнир", status: "running" });
    const petr = aPlayer({ id: 3, name: "Пётр Сидоров", phone: "+79131110003" });
    fakeBackend({
      loggedIn: true,
      tournaments: { live: [live], upcoming: [], past: [] },
      players: [IVAN, MARIA, petr],
      registrations: {
        7: [
          { player: IVAN, status: "in_game" },
          { player: MARIA, status: "out" },
          { player: petr, status: "registered" },
        ],
      },
      // Late registration is open, dropping out is not.
      registrationOpen: true,
      dropOutOpen: false,
      checkInOpen: false,
    });
    await openRegistrations("Субботний турнир");

    const list = registered();
    expect(await within(list).findByRole("listitem", { name: "Иван Петров" })).toHaveTextContent("В игре");
    expect(within(list).getByRole("listitem", { name: "Мария Иванова" })).toHaveTextContent("Игра окончена");
    expect(within(list).queryByRole("button", { name: "Снять с регистрации" })).not.toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Найти игрока клуба" })).toBeInTheDocument();
  });
});

describe("registrations made elsewhere", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  /** A player signs up in the Telegram bot: the backend has them registered at once. */
  async function signUpInTheBot(player: Player) {
    await fetch(`/api/clubs/${ME.club.id}/tournaments/${FRIDAY.id}/registrations`, {
      method: "POST",
      body: JSON.stringify({ player_id: player.id }),
    });
  }

  it("shows a player who signed up in the Telegram bot without reloading the page", async () => {
    fakeBackend({ loggedIn: true, tournaments: { upcoming: [FRIDAY], past: [] }, players: [MARIA] });
    const sockets = fakeWebSockets();
    await openRegistrations();
    expect(await screen.findByText("Пока никто не зарегистрирован")).toBeInTheDocument();
    expect(sockets.map((socket) => socket.url)).toEqual([
      `ws://localhost:3000/api/clubs/${ME.club.id}/tournaments/${FRIDAY.id}/ws`,
    ]);
    act(() => sockets[0].open());

    await signUpInTheBot(MARIA);
    act(() => sockets[0].signalChange());

    // The list replaces "nobody registered yet" once the page has read it afresh.
    const list = await screen.findByRole("list", { name: "Зарегистрированные игроки" });
    expect(within(list).getByRole("listitem", { name: "Мария Иванова" })).toHaveTextContent(
      "Зарегистрирован",
    );
  });

  it("reads the list afresh once a lost connection is back, so nothing missed meanwhile is lost", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fakeBackend({ loggedIn: true, tournaments: { upcoming: [FRIDAY], past: [] }, players: [MARIA] });
    const sockets = fakeWebSockets();
    await openRegistrations();
    act(() => sockets[0].open());

    act(() => sockets[0].drop());
    await signUpInTheBot(MARIA);
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(sockets).toHaveLength(2);
    act(() => sockets[1].open());

    const list = await screen.findByRole("list", { name: "Зарегистрированные игроки" });
    expect(within(list).getByRole("listitem", { name: "Мария Иванова" })).toBeInTheDocument();
  });

  it("stops listening once the admin leaves the tournament", async () => {
    fakeBackend({ loggedIn: true, tournaments: { upcoming: [FRIDAY], past: [] } });
    const sockets = fakeWebSockets();
    const user = await openRegistrations();

    await user.click(screen.getByRole("button", { name: "Назад к списку" }));

    expect(sockets[0].closedByPage).toBe(true);
  });
});
