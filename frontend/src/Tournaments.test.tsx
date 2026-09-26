import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { aTournament, fakeBackend } from "./testing/fakeBackend";

function sentBody(fetch: ReturnType<typeof fakeBackend>, method: string, url: RegExp) {
  const call = fetch.mock.calls.find(([calledUrl, init]) => init?.method === method && url.test(calledUrl));
  return call && JSON.parse(String(call[1]?.body));
}

function buttonNames(element: HTMLElement) {
  return within(element)
    .queryAllByRole("button")
    .map((button) => button.textContent);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("club tournaments", () => {
  it("lists the club's live, upcoming and past tournaments", async () => {
    fakeBackend({
      loggedIn: true,
      tournaments: {
        live: [aTournament({ id: 4, name: "Субботний турнир", status: "running" })],
        upcoming: [
          aTournament({ id: 1, name: "Пятничный турнир", starts_at: "2026-10-02T12:00:00Z" }),
          aTournament({ id: 2, name: "Отменённый турнир", status: "cancelled" }),
        ],
        past: [
          aTournament({
            id: 3,
            name: "Летний кубок",
            starts_at: "2026-08-01T12:00:00Z",
            status: "finished",
          }),
        ],
      },
    });

    render(<App />);

    const live = await screen.findByRole("region", { name: "Идут сейчас" });
    const saturday = within(live).getByRole("listitem", { name: "Субботний турнир" });
    expect(saturday).toHaveTextContent("Идёт");
    expect(buttonNames(saturday)).toEqual(["Регистрации", "Проведение"]);

    const upcoming = screen.getByRole("region", { name: "Предстоящие" });
    const friday = within(upcoming).getByRole("listitem", { name: "Пятничный турнир" });
    expect(friday).toHaveTextContent("2 октября");
    expect(friday).toHaveTextContent("19:00");
    expect(friday).toHaveTextContent("2 000 ₽");
    expect(buttonNames(friday)).toEqual(["Регистрации", "Проведение", "Изменить", "Отменить турнир"]);
    const cancelled = within(upcoming).getByRole("listitem", { name: "Отменённый турнир" });
    expect(cancelled).toHaveTextContent("Отменён");
    expect(buttonNames(cancelled)).toEqual(["Регистрации"]);  // no running, editing or cancelling

    const past = screen.getByRole("region", { name: "Прошедшие" });
    const summer = within(past).getByRole("listitem", { name: "Летний кубок" });
    expect(summer).toHaveTextContent("1 августа");
    expect(summer).toHaveTextContent("Завершён");
    expect(buttonNames(summer)).toEqual(["Регистрации", "Проведение"]);  // no editing or cancelling
  });

  it("shows no live section while nothing is running", async () => {
    fakeBackend({ loggedIn: true, tournaments: { upcoming: [aTournament()], past: [] } });

    render(<App />);

    await screen.findByRole("region", { name: "Предстоящие" });
    expect(screen.queryByRole("region", { name: "Идут сейчас" })).not.toBeInTheDocument();
  });

  it("creates a tournament from a league template with an adjusted structure", async () => {
    const fetch = fakeBackend({ loggedIn: true });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Создать турнир" }));
    expect(await screen.findByLabelText("Шаблон структуры")).toHaveDisplayValue("Стандартная лиги");
    await user.type(screen.getByLabelText("Название"), "Осенний кубок");
    fireEvent.change(screen.getByLabelText("Начало"), { target: { value: "2026-10-03T19:00" } });
    await user.type(screen.getByLabelText("Бай-ин, ₽"), "2000");
    await user.type(screen.getByLabelText("Стартовый стек"), "20000");
    const bigBlind = screen.getByLabelText("Уровень 1: большой блайнд");
    await user.clear(bigBlind);
    await user.type(bigBlind, "250");
    await user.click(screen.getByRole("button", { name: "Удалить уровень 2" }));
    await user.click(screen.getByRole("button", { name: "Добавить уровень" }));
    await user.click(screen.getByRole("button", { name: "Добавить перерыв после уровня 2" }));
    await user.type(screen.getByLabelText("Re-entry до уровня"), "2");
    await user.type(screen.getByLabelText("Add-on на уровне"), "2");
    const seats = screen.getByLabelText("Мест за столом");
    expect(seats).toHaveValue(9);
    await user.clear(seats);
    await user.type(seats, "8");
    await user.click(screen.getByRole("button", { name: "Сохранить турнир" }));

    const upcoming = await screen.findByRole("region", { name: "Предстоящие" });
    expect(within(upcoming).getByRole("listitem", { name: "Осенний кубок" })).toBeInTheDocument();
    expect(sentBody(fetch, "POST", /\/api\/clubs\/7\/tournaments$/)).toEqual({
      name: "Осенний кубок",
      starts_at: "2026-10-03T12:00:00.000Z",
      buy_in: 2000,
      starting_stack: 20000,
      structure: [
        { kind: "level", small_blind: 100, big_blind: 250, ante: 0, duration_minutes: 20 },
        { kind: "break", duration_minutes: 10 },
        { kind: "level", small_blind: 300, big_blind: 600, ante: 75, duration_minutes: 20 },
        { kind: "break", duration_minutes: 10 },
        { kind: "level", small_blind: 600, big_blind: 1200, ante: 150, duration_minutes: 20 },
      ],
      reentry_until_level: 2,
      addon_at_level: 2,
      late_registration_until_level: null,
      seats_per_table: 8,
    });
  });

  it("shows why the server rejected the tournament and keeps what was typed", async () => {
    fakeBackend({
      loggedIn: true,
      rejectWith: [
        "Время начала уже прошло",
        "Add-on: уровня 12 нет в структуре, в ней уровни с 1 по 3",
      ],
    });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Создать турнир" }));
    await user.type(await screen.findByLabelText("Название"), "Осенний кубок");
    fireEvent.change(screen.getByLabelText("Начало"), { target: { value: "2020-01-01T19:00" } });
    await user.type(screen.getByLabelText("Бай-ин, ₽"), "2000");
    await user.type(screen.getByLabelText("Стартовый стек"), "20000");
    await user.type(screen.getByLabelText("Add-on на уровне"), "12");
    await user.click(screen.getByRole("button", { name: "Сохранить турнир" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Время начала уже прошло");
    expect(alert).toHaveTextContent("Add-on: уровня 12 нет в структуре, в ней уровни с 1 по 3");
    expect(screen.getByLabelText("Название")).toHaveValue("Осенний кубок");
    expect(screen.getByLabelText("Add-on на уровне")).toHaveValue(12);
  });

  it("edits an upcoming tournament", async () => {
    const fetch = fakeBackend({
      loggedIn: true,
      tournaments: {
        upcoming: [aTournament({ id: 5, name: "Пятничный турнир", starts_at: "2026-10-02T12:00:00Z" })],
        past: [],
      },
    });
    const user = userEvent.setup();
    render(<App />);

    const row = await screen.findByRole("listitem", { name: "Пятничный турнир" });
    await user.click(within(row).getByRole("button", { name: "Изменить" }));
    expect(
      screen.getByRole("heading", { name: "Изменить турнир «Пятничный турнир»" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Начало")).toHaveValue("2026-10-02T19:00");
    expect(screen.getByLabelText("Уровень 3: анте")).toHaveValue(75);
    expect(screen.getByLabelText("Поздняя регистрация до уровня")).toHaveValue(3);
    const buyIn = screen.getByLabelText("Бай-ин, ₽");
    await user.clear(buyIn);
    await user.type(buyIn, "1500");
    await user.clear(screen.getByLabelText("Add-on на уровне"));
    await user.click(screen.getByRole("button", { name: "Сохранить турнир" }));

    const edited = await screen.findByRole("listitem", { name: "Пятничный турнир" });
    expect(edited).toHaveTextContent("1 500 ₽");
    expect(sentBody(fetch, "PUT", /\/api\/clubs\/7\/tournaments\/5$/)).toEqual({
      ...aTournament(),
      id: undefined,
      status: undefined,
      name: "Пятничный турнир",
      starts_at: "2026-10-02T12:00:00.000Z",
      buy_in: 1500,
      addon_at_level: null,
    });
  });

  it("cancels an upcoming tournament after the admin confirms", async () => {
    const fetch = fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [aTournament({ id: 5, name: "Пятничный турнир" })], past: [] },
    });
    const confirm = vi.fn(() => true);
    vi.stubGlobal("confirm", confirm);
    const user = userEvent.setup();
    render(<App />);

    const row = await screen.findByRole("listitem", { name: "Пятничный турнир" });
    await user.click(within(row).getByRole("button", { name: "Отменить турнир" }));

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("«Пятничный турнир»"));
    expect(await within(row).findByText("Отменён")).toBeInTheDocument();
    expect(buttonNames(row)).toEqual(["Регистрации"]);  // no editing or cancelling
    expect(fetch).toHaveBeenCalledWith(
      "/api/clubs/7/tournaments/5/cancel",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("keeps the tournament when the admin changes their mind", async () => {
    const fetch = fakeBackend({
      loggedIn: true,
      tournaments: { upcoming: [aTournament({ id: 5, name: "Пятничный турнир" })], past: [] },
    });
    vi.stubGlobal("confirm", () => false);
    const user = userEvent.setup();
    render(<App />);

    const row = await screen.findByRole("listitem", { name: "Пятничный турнир" });
    await user.click(within(row).getByRole("button", { name: "Отменить турнир" }));

    expect(within(row).queryByText("Отменён")).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalledWith(expect.stringMatching(/cancel$/), expect.anything());
  });

  it("replaces the structure with another league template", async () => {
    fakeBackend({ loggedIn: true });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Создать турнир" }));
    expect(await screen.findByLabelText("Уровень 3: анте")).toHaveValue(75);
    await user.selectOptions(screen.getByLabelText("Шаблон структуры"), "Турбо");

    expect(screen.getByLabelText("Уровень 1: минут")).toHaveValue(10);
    expect(screen.getByLabelText("Уровень 2: минут")).toHaveValue(10);
    expect(screen.queryByLabelText("Уровень 3: анте")).not.toBeInTheDocument();
  });
});
