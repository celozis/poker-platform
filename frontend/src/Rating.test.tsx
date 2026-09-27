import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { ClubRating } from "./api";
import { aPlayer, fakeBackend } from "./testing/fakeBackend";

afterEach(() => {
  vi.unstubAllGlobals();
});

const IVAN = aPlayer({ id: 1, name: "Иван Петров" });
const MARIA = aPlayer({ id: 2, name: "Мария Иванова" });
const PETR = aPlayer({ id: 3, name: "Пётр Сидоров" });

const CURRENT: ClubRating = {
  season: {
    id: "2026-2",
    name: "2-е полугодие 2026",
    first_day: "2026-07-01",
    last_day: "2026-12-31",
  },
  previous_season: "2026-1",
  next_season: null,
  players: [
    { position: 1, player: MARIA, points: 17, tournaments: 2 },
    { position: 2, player: IVAN, points: 4, tournaments: 2 },
    { position: 2, player: PETR, points: 4, tournaments: 1 },
  ],
};

const EARLIER: ClubRating = {
  season: {
    id: "2026-1",
    name: "1-е полугодие 2026",
    first_day: "2026-01-01",
    last_day: "2026-06-30",
  },
  previous_season: "2025-2",
  next_season: "2026-2",
  players: [{ position: 1, player: PETR, points: 21, tournaments: 3 }],
};

async function openRating(ratings: ClubRating[] = [CURRENT, EARLIER]) {
  const fetch = fakeBackend({ loggedIn: true, ratings });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Рейтинг" }));
  return { user, fetch };
}

function rows() {
  const [, ...players] = within(screen.getByRole("table", { name: "Рейтинг клуба" })).getAllByRole(
    "row",
  );
  return players.map((row) => within(row).getAllByRole("cell").map((cell) => cell.textContent));
}

describe("club rating", () => {
  it("shows the players of the current season by points", async () => {
    await openRating();

    expect(await screen.findByText("2-е полугодие 2026")).toBeInTheDocument();
    expect(screen.getByText("1 июля — 31 декабря 2026")).toBeInTheDocument();
    expect(rows()).toEqual([
      ["1", "Мария Иванова", "2", "17"],
      ["2", "Иван Петров", "2", "4"],
      ["2", "Пётр Сидоров", "1", "4"],
    ]);
    expect(screen.queryByRole("button", { name: "Следующий сезон" })).not.toBeInTheDocument();
  });

  it("looks back at the season before and returns", async () => {
    const { user, fetch } = await openRating();

    await user.click(await screen.findByRole("button", { name: "Предыдущий сезон" }));

    expect(await screen.findByText("1-е полугодие 2026")).toBeInTheDocument();
    expect(screen.getByText("1 января — 30 июня 2026")).toBeInTheDocument();
    expect(rows()).toEqual([["1", "Пётр Сидоров", "3", "21"]]);
    expect(fetch).toHaveBeenCalledWith("/api/clubs/7/rating?season=2026-1");

    await user.click(screen.getByRole("button", { name: "Следующий сезон" }));

    expect(await screen.findByText("2-е полугодие 2026")).toBeInTheDocument();
  });

  it("says when nobody has played a finished tournament this season", async () => {
    await openRating([{ ...CURRENT, players: [] }]);

    expect(
      await screen.findByText("В этом сезоне ещё нет завершённых турниров"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
