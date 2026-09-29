import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { GameState } from "./api";
import { aGame, aPlayer, aSeat, aTournament, fakeBackend, ME } from "./testing/fakeBackend";
import { fakeWebSockets } from "./testing/fakeWebSocket";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const IVAN = aPlayer({ id: 1, name: "Иван Петров", phone: "+79135551234" });
const MARIA = aPlayer({ id: 2, name: "Мария Иванова", phone: "+79131110002" });
const PETR = aPlayer({ id: 3, name: "Пётр Сидоров", phone: "+79131110003" });
// Level 1 and level 2 of 20 minutes, a 10-minute break, level 3 with an ante.
const FRIDAY = aTournament({ id: 5, name: "Пятничный турнир" });

function running(overrides: Partial<GameState> = {}): GameState {
  return aGame({
    status: "running",
    clock: { running: true, item: 0, seconds_left: 20 * 60 },
    in_game: [aSeat(IVAN, 1, 1), aSeat(MARIA, 1, 2), aSeat(PETR, 1, 3)],
    ...overrides,
  });
}

async function openGame(game: GameState, options: Parameters<typeof fakeBackend>[0] = {}) {
  const fetch = fakeBackend({
    loggedIn: true,
    tournaments: { upcoming: [FRIDAY], past: [] },
    players: [IVAN, MARIA, PETR],
    games: { 5: game },
    ...options,
  });
  const user = userEvent.setup(vi.isFakeTimers() ? { advanceTimers: vi.advanceTimersByTime } : {});
  render(<App />);
  const row = await screen.findByRole("listitem", { name: "Пятничный турнир" });
  await user.click(within(row).getByRole("button", { name: "Проведение" }));
  await screen.findByRole("heading", { name: "Пятничный турнир" });
  return { user, fetch };
}

function clock() {
  return screen.getByRole("region", { name: "Блайнды" });
}

function table(name: string) {
  return screen.getByRole("region", { name });
}

describe("running a tournament", () => {
  it("starts the tournament and seats everyone who has come", async () => {
    const { user } = await openGame(
      aGame({
        waiting: [
          { player: IVAN, status: "checked_in" },
          { player: MARIA, status: "checked_in" },
          { player: PETR, status: "registered" },
        ],
      }),
    );
    expect(await screen.findByText("Пришли: 2 из 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Начать турнир" }));

    const first = await screen.findByRole("region", { name: "Стол 1" });
    expect(within(first).getByRole("listitem", { name: "Иван Петров" })).toHaveTextContent("Место 1");
    expect(within(first).getByRole("listitem", { name: "Мария Иванова" })).toHaveTextContent("Место 2");
    expect(clock()).toHaveTextContent("Уровень 1");
    expect(clock()).toHaveTextContent("100 / 200");
    expect(clock()).toHaveTextContent("20:00");
    expect(clock()).toHaveTextContent("Дальше: уровень 2 · 200 / 400");
    expect(screen.getByText("Идёт")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Начать турнир" })).not.toBeInTheDocument();
  });

  it("gives the link of the hall board, which opens without login", async () => {
    await openGame(aGame());

    const link = await screen.findByRole("link", { name: "Открыть табло" });
    expect(link).toHaveAttribute("href", "/board/3f9a1c2b7d4e");
    expect(link).toHaveAttribute("target", "_blank");
    expect(screen.getByText("http://localhost:3000/board/3f9a1c2b7d4e")).toBeInTheDocument();
  });

  it("explains why the tournament did not start", async () => {
    const { user } = await openGame(aGame({ waiting: [{ player: IVAN, status: "checked_in" }] }));

    await user.click(await screen.findByRole("button", { name: "Начать турнир" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Для старта нужны хотя бы два пришедших игрока",
    );
  });

  it("counts the level down and asks the server again when it is over", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { fetch } = await openGame(running({ clock: { running: true, item: 0, seconds_left: 65 } }));
    expect(await within(clock()).findByText("01:05")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(within(clock()).getByText("01:02")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(63000));
    const gameCalls = fetch.mock.calls.filter(([url]) => url === "/api/clubs/7/tournaments/5/game");
    expect(gameCalls.length).toBe(2);
  });

  it("pauses and resumes the clock and switches levels", async () => {
    const { user } = await openGame(running());

    await user.click(await screen.findByRole("button", { name: "Пауза" }));
    expect(await screen.findByRole("button", { name: "Продолжить" })).toBeInTheDocument();
    expect(clock()).toHaveTextContent("на паузе");

    await user.click(screen.getByRole("button", { name: "Следующий уровень" }));
    expect(await within(clock()).findByText("Уровень 2")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Следующий уровень" }));
    expect(await within(clock()).findByText("Перерыв")).toBeInTheDocument();
    expect(clock()).toHaveTextContent("10:00");
    expect(clock()).toHaveTextContent("Дальше: уровень 3 · 300 / 600, анте 75");
    await user.click(screen.getByRole("button", { name: "Предыдущий уровень" }));
    expect(await within(clock()).findByText("Уровень 2")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Продолжить" }));
    expect(await screen.findByRole("button", { name: "Пауза" })).toBeInTheDocument();
  });

  it("knocks a player out after the admin confirms and shows their place", async () => {
    const confirm = vi.fn(() => true);
    vi.stubGlobal("confirm", confirm);
    const { user } = await openGame(running());
    const ivan = await within(table("Стол 1")).findByRole("listitem", { name: "Иван Петров" });

    await user.click(within(ivan).getByRole("button", { name: "Отметить выбывание" }));

    expect(confirm).toHaveBeenCalledWith("Игрок Иван Петров выбыл?");
    const out = await screen.findByRole("list", { name: "Выбывшие" });
    expect(within(out).getByRole("listitem", { name: "Иван Петров" })).toHaveTextContent("3 место");
    expect(within(table("Стол 1")).queryByRole("listitem", { name: "Иван Петров" })).toBeNull();
  });

  it("finishes the tournament when one player is left and shows the places", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    const { user } = await openGame(running({ in_game: [aSeat(IVAN, 1, 1), aSeat(MARIA, 1, 2)] }));
    const ivan = await within(table("Стол 1")).findByRole("listitem", { name: "Иван Петров" });

    await user.click(within(ivan).getByRole("button", { name: "Отметить выбывание" }));

    expect(await screen.findByText("Турнир завершён")).toBeInTheDocument();
    const results = screen.getByRole("list", { name: "Итоги" });
    expect(within(results).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      expect.stringContaining("1 место"),
      expect.stringContaining("2 место"),
    ]);
    expect(within(results).getAllByRole("listitem")[0]).toHaveTextContent("Мария Иванова");
    expect(within(results).getAllByRole("listitem")[0]).toHaveTextContent("4 очка");
    expect(within(results).getAllByRole("listitem")[1]).toHaveTextContent("0 очков");
    expect(within(results).queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Пауза" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Начать турнир" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Результаты и исправление мест" }));

    expect(await screen.findByRole("heading", { name: "Результаты" })).toBeInTheDocument();
  });

  it("takes the payment for a re-entry and an add-on while their windows are open", async () => {
    const { user, fetch } = await openGame(
      running({
        windows: { reentry: true, addon: true, late_registration: false },
        in_game: [aSeat(MARIA, 1, 2), aSeat(PETR, 1, 3)],
        out: [{ player: IVAN, place: 3, reentries: 0, addons: 0, points: null }],
      }),
    );
    const out = await screen.findByRole("list", { name: "Выбывшие" });

    await user.click(within(within(out).getByRole("listitem", { name: "Иван Петров" })).getByRole("button", { name: "Re-entry" }));
    const reentryPayment = screen.getByRole("dialog", { name: "Оплата" });
    expect(reentryPayment).toHaveTextContent("Re-entry: Иван Петров");
    expect(reentryPayment).toHaveTextContent("2 000 ₽");
    await user.click(within(reentryPayment).getByRole("button", { name: "Наличные" }));
    const ivan = await within(table("Стол 1")).findByRole("listitem", { name: "Иван Петров" });
    expect(ivan).toHaveTextContent("re-entry: 1");
    const maria = within(table("Стол 1")).getByRole("listitem", { name: "Мария Иванова" });
    await user.click(within(maria).getByRole("button", { name: "Add-on" }));
    const addonPayment = screen.getByRole("dialog", { name: "Оплата" });
    expect(addonPayment).toHaveTextContent("Add-on: Мария Иванова");
    expect(addonPayment).toHaveTextContent("1 000 ₽");
    await user.click(within(addonPayment).getByRole("button", { name: "Карта" }));

    expect(await within(maria).findByText("add-on: 1")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/clubs/7/tournaments/5/players/1/reentry",
      expect.objectContaining({ body: JSON.stringify({ payment_method: "cash" }) }),
    );
    expect(fetch).toHaveBeenCalledWith(
      "/api/clubs/7/tournaments/5/players/2/addon",
      expect.objectContaining({ body: JSON.stringify({ payment_method: "card" }) }),
    );
    // One add-on per entry: Maria has used hers, Ivan has two entries and no add-on yet.
    expect(within(maria).queryByRole("button", { name: "Add-on" })).not.toBeInTheDocument();
    expect(within(ivan).getByRole("button", { name: "Add-on" })).toBeInTheDocument();
    expect(screen.getByText("Re-entry открыт до уровня 2")).toBeInTheDocument();
    expect(screen.getByText("Сейчас можно взять add-on")).toBeInTheDocument();
  });

  it("offers neither re-entry nor add-on once their windows have closed", async () => {
    await openGame(running({ out: [{ player: IVAN, place: 3, reentries: 0, addons: 0, points: null }], in_game: [aSeat(MARIA, 1, 2), aSeat(PETR, 1, 3)] }));

    const out = await screen.findByRole("list", { name: "Выбывшие" });
    expect(within(out).queryByRole("button", { name: "Re-entry" })).not.toBeInTheDocument();
    expect(within(table("Стол 1")).queryByRole("button", { name: "Add-on" })).not.toBeInTheDocument();
  });

  it("undoes a knock-out marked by mistake", async () => {
    const { user } = await openGame(
      running({
        in_game: [aSeat(MARIA, 1, 2), aSeat(PETR, 1, 3)],
        out: [{ player: IVAN, place: 3, reentries: 0, addons: 0, points: null }],
      }),
    );
    const out = await screen.findByRole("list", { name: "Выбывшие" });

    await user.click(
      within(within(out).getByRole("listitem", { name: "Иван Петров" })).getByRole("button", {
        name: "Отменить выбывание",
      }),
    );

    const ivan = await within(table("Стол 1")).findByRole("listitem", { name: "Иван Петров" });
    expect(ivan).not.toHaveTextContent("re-entry");
    expect(screen.queryByRole("list", { name: "Выбывшие" })).not.toBeInTheDocument();
  });

  it("suggests a move to keep tables even and makes it", async () => {
    const { user } = await openGame(
      running({
        seats_per_table: 3,
        in_game: [aSeat(IVAN, 1, 1), aSeat(MARIA, 2, 1), aSeat(PETR, 2, 2)],
        suggested_move: { player: PETR, from_table: 2, from_seat: 2, to_table: 1, to_seat: 2 },
      }),
    );

    const suggestion = await screen.findByRole("status", { name: "Пересадка" });
    expect(suggestion).toHaveTextContent("Пётр Сидоров: стол 2, место 2 → стол 1, место 2");
    await user.click(within(suggestion).getByRole("button", { name: "Пересадить" }));

    expect(
      await within(table("Стол 1")).findByRole("listitem", { name: "Пётр Сидоров" }),
    ).toHaveTextContent("Место 2");
    expect(screen.queryByRole("status", { name: "Пересадка" })).not.toBeInTheDocument();
  });

  it("calls the last table the final table", async () => {
    await openGame(
      running({
        seats_per_table: 3,
        in_game: [aSeat(IVAN, 1, 1), aSeat(MARIA, 1, 2)],
        out: [
          { player: PETR, place: 3, reentries: 0, addons: 0, points: null },
          { player: aPlayer({ id: 4, name: "Олег Орлов" }), place: 4, reentries: 0, addons: 0, points: null },
        ],
      }),
    );

    expect(await screen.findByRole("region", { name: "Финальный стол" })).toBeInTheDocument();
  });

  it("seats a late player, who pays the buy-in, while late registration is open", async () => {
    const { user, fetch } = await openGame(
      running({
        windows: { reentry: false, addon: false, late_registration: true },
        waiting: [{ player: aPlayer({ id: 4, name: "Олег Орлов" }), status: "registered" }],
      }),
      { players: [IVAN, MARIA, PETR, aPlayer({ id: 4, name: "Олег Орлов" })] },
    );
    const late = await screen.findByRole("region", { name: "Поздняя регистрация" });

    await user.click(
      within(within(late).getByRole("listitem", { name: "Олег Орлов" })).getByRole("button", {
        name: "Посадить",
      }),
    );
    const payment = screen.getByRole("dialog", { name: "Оплата" });
    expect(payment).toHaveTextContent("Бай-ин: Олег Орлов");
    await user.click(within(payment).getByRole("button", { name: "Карта" }));

    expect(
      await within(table("Стол 1")).findByRole("listitem", { name: "Олег Орлов" }),
    ).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/clubs/7/tournaments/5/players/4/seat",
      expect.objectContaining({ body: JSON.stringify({ payment_method: "card" }) }),
    );
  });

  it("registers and seats a newcomer found by name during late registration", async () => {
    const { user } = await openGame(
      running({ windows: { reentry: false, addon: false, late_registration: true } }),
      { players: [IVAN, MARIA, PETR, aPlayer({ id: 4, name: "Олег Орлов" })] },
    );
    const late = await screen.findByRole("region", { name: "Поздняя регистрация" });

    await user.type(within(late).getByRole("searchbox", { name: "Найти игрока клуба" }), "Олег");
    const found = await within(late).findByRole("list", { name: "Найденные игроки" });
    await user.click(
      within(within(found).getByRole("listitem", { name: "Олег Орлов" })).getByRole("button", {
        name: "Посадить",
      }),
    );
    await user.click(
      within(screen.getByRole("dialog", { name: "Оплата" })).getByRole("button", { name: "Наличные" }),
    );

    expect(
      await within(table("Стол 1")).findByRole("listitem", { name: "Олег Орлов" }),
    ).toBeInTheDocument();
  });

  it("opens the tournament's cashier from its running", async () => {
    const { user } = await openGame(running());

    await user.click(await screen.findByRole("button", { name: "Касса" }));

    expect(await screen.findByRole("heading", { name: "Сводка" })).toBeInTheDocument();
  });

  it("sends an action once however quickly the admin clicks again", async () => {
    const { user, fetch } = await openGame(running());
    await screen.findByRole("button", { name: "Следующий уровень" });
    // The server takes its time with the first click.
    fetch.mockImplementationOnce(() => new Promise(() => {}));

    await user.click(screen.getByRole("button", { name: "Следующий уровень" }));
    await user.click(screen.getByRole("button", { name: "Следующий уровень" }));

    const sent = fetch.mock.calls.filter(([url]) => String(url).endsWith("/next-level"));
    expect(sent).toHaveLength(1);
  });

  it("shows a player who signed up in the Telegram bot during late registration without reloading", async () => {
    const sockets = fakeWebSockets();
    await openGame(
      running({
        in_game: [aSeat(IVAN, 1, 1), aSeat(MARIA, 1, 2)],
        windows: { reentry: false, addon: false, late_registration: true },
      }),
    );
    expect(sockets.map((socket) => socket.url)).toEqual([
      `ws://localhost:3000/api/clubs/${ME.club.id}/tournaments/${FRIDAY.id}/ws`,
    ]);
    act(() => sockets[0].open());

    await fetch(`/api/clubs/${ME.club.id}/tournaments/${FRIDAY.id}/registrations`, {
      method: "POST",
      body: JSON.stringify({ player_id: PETR.id }),
    });
    act(() => sockets[0].signalChange());

    const waiting = await screen.findByRole("list", { name: "Ждут посадки" });
    expect(within(waiting).getByRole("listitem", { name: "Пётр Сидоров" })).toBeInTheDocument();
  });
});
