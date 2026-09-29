import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { ClubReport } from "./api";
import { aPlayer, fakeBackend, ME } from "./testing/fakeBackend";

afterEach(() => {
  vi.unstubAllGlobals();
});

const IVAN = aPlayer({ id: 1, name: "Иван Петров" });
const MARIA = aPlayer({ id: 2, name: "Мария Иванова" });

const SEPTEMBER: ClubReport = {
  finances: {
    tournaments: 2,
    by_kind: [
      { kind: "buy_in", count: 5, amount: 9000 },
      { kind: "reentry", count: 1, amount: 2000 },
      { kind: "addon", count: 1, amount: 1000 },
    ],
    by_method: [
      { payment_method: "cash", amount: 8000 },
      { payment_method: "card", amount: 4000 },
    ],
    total: 12000,
  },
  attendance: {
    weeks: [
      { first_day: "2026-09-01", last_day: "2026-09-06", tournaments: 0, participants: 0 },
      { first_day: "2026-09-07", last_day: "2026-09-13", tournaments: 2, participants: 7 },
    ],
    participants: 7,
    average_players: 3.5,
  },
  top_by_points: [
    { position: 1, player: MARIA, points: 17, tournaments: 1 },
    { position: 2, player: IVAN, points: 4, tournaments: 2 },
  ],
  top_by_tournaments: [
    { position: 1, player: IVAN, points: 4, tournaments: 2 },
    { position: 2, player: MARIA, points: 17, tournaments: 1 },
  ],
};

async function openReports(report: ClubReport = SEPTEMBER) {
  const fetch = fakeBackend({ loggedIn: true, role: "owner", report });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Отчёты" }));
  return { user, fetch };
}

function pickPeriod(from: string, to: string) {
  fireEvent.change(screen.getByLabelText("С"), { target: { value: from } });
  fireEvent.change(screen.getByLabelText("По"), { target: { value: to } });
}

/** Amounts are written with a non-breaking space ("4 000 ₽"); compared with a plain one. */
const plain = (text: string | null) => (text ?? "").replace(/\s/g, " ");

function rows(table: string) {
  const [, ...body] = within(screen.getByRole("table", { name: table })).getAllByRole("row");
  return body.map((row) => within(row).getAllByRole("cell").map((cell) => plain(cell.textContent)));
}

describe("club owner's reports", () => {
  it("are a section of the owner's admin panel, next to what an admin does", async () => {
    fakeBackend({ loggedIn: true, role: "owner" });
    render(<App />);

    expect(await screen.findByRole("button", { name: "Отчёты" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Турниры" })).toBeInTheDocument();
  });

  it("are not shown to an admin", async () => {
    fakeBackend({ loggedIn: true });
    render(<App />);

    expect(await screen.findByRole("button", { name: "Турниры" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Отчёты" })).not.toBeInTheDocument();
  });
});

describe("a report of a period", () => {
  it("shows the money, the attendance and the best players of the period picked", async () => {
    const { fetch } = await openReports();

    pickPeriod("2026-09-01", "2026-09-30");

    expect(await screen.findByText("Турниров проведено: 2")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(`/api/clubs/${ME.club.id}/reports?from=2026-09-01&to=2026-09-30`);
    expect(rows("Выручка по операциям")).toEqual([
      ["Бай-ин", "5", "9 000 ₽"],
      ["Re-entry", "1", "2 000 ₽"],
      ["Add-on", "1", "1 000 ₽"],
    ]);
    expect(rows("Выручка по способам оплаты")).toEqual([
      ["Наличные", "8 000 ₽"],
      ["Карта", "4 000 ₽"],
    ]);
    expect(screen.getByText(/Всего:/)).toHaveTextContent("Всего: 12 000 ₽");
    expect(rows("Посещаемость по неделям")).toEqual([
      ["01.09 – 06.09", "0", "0"],
      ["07.09 – 13.09", "2", "7"],
    ]);
    expect(screen.getByText("В среднем 3,5 игрока на турнир")).toBeInTheDocument();
    expect(rows("Лучшие по очкам")).toEqual([
      ["1", "Мария Иванова", "17", "1"],
      ["2", "Иван Петров", "4", "2"],
    ]);
    expect(rows("Лучшие по числу турниров")).toEqual([
      ["1", "Иван Петров", "2", "4"],
      ["2", "Мария Иванова", "1", "17"],
    ]);
    expect(screen.getByRole("link", { name: "Выгрузить в CSV" })).toHaveAttribute(
      "href",
      `/api/clubs/${ME.club.id}/reports.csv?from=2026-09-01&to=2026-09-30`,
    );
  });

  it("says why a period will not do", async () => {
    await openReports();

    pickPeriod("2026-09-30", "2026-09-01");

    expect(await screen.findByRole("alert")).toHaveTextContent("Период: начало позже конца");
    expect(screen.queryByRole("link", { name: "Выгрузить в CSV" })).not.toBeInTheDocument();
  });

  it("says when the period had no tournaments", async () => {
    await openReports({
      ...SEPTEMBER,
      finances: { ...SEPTEMBER.finances, tournaments: 0 },
      attendance: { weeks: [], participants: 0, average_players: null },
      top_by_points: [],
      top_by_tournaments: [],
    });

    expect(await screen.findByText("Турниров не было")).toBeInTheDocument();
    expect(screen.getByText("За период нет завершённых турниров")).toBeInTheDocument();
  });

  it("shows nothing of the last period once a day of it is cleared", async () => {
    await openReports();
    pickPeriod("2026-09-01", "2026-09-30");
    await screen.findByText("Турниров проведено: 2");

    fireEvent.change(screen.getByLabelText("С"), { target: { value: "" } });

    expect(screen.getByText("Выберите начало и конец периода")).toBeInTheDocument();
    expect(screen.queryByText("Турниров проведено: 2")).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Выгрузить в CSV" })).not.toBeInTheDocument();
  });
});
