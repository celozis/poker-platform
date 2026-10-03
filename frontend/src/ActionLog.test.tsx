import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { ActionLogEntry } from "./api";
import { aGame, aPlayer, aTournament, fakeBackend, ME } from "./testing/fakeBackend";

afterEach(() => {
  vi.unstubAllGlobals();
});

const IVAN = aPlayer({ id: 1, name: "Иван Петров" });
const MARIA = aPlayer({ id: 2, name: "Мария Иванова", phone: "+79135550000" });
const FRIDAY = aTournament({ id: 5, name: "Пятничный турнир", status: "running" });

function entry(
  id: number,
  action: ActionLogEntry["action"],
  player: ActionLogEntry["player"],
  admin: ActionLogEntry["admin"],
  details = "",
  created_at = "2026-10-02T12:05:00Z",
): ActionLogEntry {
  return { id, created_at, action, player, admin, details };
}

// As the backend answers: the latest first. Maria signed up in the bot herself.
const LOG = [
  entry(4, "knocked_out", IVAN, ME.admin, "Место 3", "2026-10-02T13:40:00Z"),
  entry(3, "started", null, ME.admin, "Игроков: 2, столов: 1", "2026-10-02T12:00:00Z"),
  entry(2, "registered", MARIA, null, "", "2026-10-01T09:30:00Z"),
  entry(1, "registered", IVAN, ME.admin, "", "2026-09-30T18:00:00Z"),
];

async function openLog(options: Parameters<typeof fakeBackend>[0] = {}) {
  const fetch = fakeBackend({
    loggedIn: true,
    tournaments: { live: [FRIDAY], upcoming: [], past: [] },
    actionLogs: { 5: LOG },
    ...options,
  });
  const user = userEvent.setup();
  render(<App />);
  const row = await screen.findByRole("listitem", { name: "Пятничный турнир" });
  await user.click(within(row).getByRole("button", { name: "Журнал" }));
  await screen.findByRole("heading", { name: "Пятничный турнир" });
  return { user, fetch };
}

function shownEntries() {
  return within(screen.getByRole("list", { name: "Журнал действий" }))
    .getAllByRole("listitem")
    .map((item) => item.textContent);
}

describe("tournament action log", () => {
  it("shows who did what, when and to whom, the latest first", async () => {
    await openLog();

    // Times in the club's time, Novosibirsk.
    await screen.findByRole("list", { name: "Журнал действий" });
    expect(shownEntries()).toEqual([
      expect.stringMatching(/2 окт\.?, 20:40.*Выбывание · Иван Петров.*Анна Соколова · Место 3/),
      expect.stringMatching(/2 окт\.?, 19:00.*Старт турнира.*Анна Соколова · Игроков: 2, столов: 1/),
      expect.stringMatching(/1 окт\.?, 16:30.*Запись на турнир · Мария Иванова.*игрок$/),
      expect.stringMatching(/1 окт\.?, 01:00.*Запись на турнир · Иван Петров.*Анна Соколова$/),
    ]);
  });

  it("names the clock adjustments and the closing of registration", async () => {
    await openLog({
      actionLogs: {
        5: [
          entry(7, "late_registration_opened", null, ME.admin, "Уровень 2, осталось 12:00"),
          entry(6, "late_registration_closed", null, ME.admin, "Уровень 2, осталось 12:30"),
          entry(5, "minute_taken", null, ME.admin, "Уровень 2: 14:00 → 13:00"),
          entry(4, "minute_added", null, ME.admin, "Уровень 2: 13:00 → 14:00"),
          entry(3, "level_restarted", null, ME.admin, "Уровень 2: 4:00 → 20:00"),
          entry(2, "registration_opened", null, ME.admin),
          entry(1, "registration_closed", null, ME.admin),
        ],
      },
    });

    await screen.findByRole("list", { name: "Журнал действий" });
    expect(shownEntries()).toEqual([
      expect.stringMatching(/Поздняя регистрация открыта.*Уровень 2, осталось 12:00/),
      expect.stringMatching(/Поздняя регистрация закрыта досрочно.*Уровень 2, осталось 12:30/),
      expect.stringMatching(/−1 минута.*Уровень 2: 14:00 → 13:00/),
      expect.stringMatching(/\+1 минута.*Уровень 2: 13:00 → 14:00/),
      expect.stringMatching(/Уровень сначала.*Уровень 2: 4:00 → 20:00/),
      expect.stringMatching(/Запись открыта/),
      expect.stringMatching(/Запись закрыта/),
    ]);
  });

  it("filters the log by player to trace one player's evening", async () => {
    const { user, fetch } = await openLog();
    const filter = await screen.findByRole("combobox", { name: "Игрок" });
    expect(within(filter).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Все игроки",
      "Иван Петров",
      "Мария Иванова",
    ]);

    await user.selectOptions(filter, "Мария Иванова");

    expect(fetch).toHaveBeenCalledWith(`/api/clubs/${ME.club.id}/tournaments/5/log?player_id=2`);
    await screen.findByText("Записей: 1");
    expect(shownEntries()).toEqual([expect.stringContaining("Запись на турнир · Мария Иванова")]);

    await user.selectOptions(filter, "Все игроки");

    expect(await screen.findByText("Записей: 4")).toBeInTheDocument();
  });

  it("says so when nothing has been done to the tournament yet", async () => {
    await openLog({ actionLogs: {} });

    expect(await screen.findByText("Записей пока нет")).toBeInTheDocument();
  });

  it("opens from the running of the tournament", async () => {
    fakeBackend({
      loggedIn: true,
      tournaments: { live: [FRIDAY], upcoming: [], past: [] },
      games: { 5: aGame({ status: "running" }) },
      actionLogs: { 5: LOG },
    });
    const user = userEvent.setup();
    render(<App />);
    const row = await screen.findByRole("listitem", { name: "Пятничный турнир" });
    await user.click(within(row).getByRole("button", { name: "Проведение" }));

    await user.click(await screen.findByRole("button", { name: "Журнал" }));

    expect(await screen.findByRole("list", { name: "Журнал действий" })).toBeInTheDocument();
  });
});
