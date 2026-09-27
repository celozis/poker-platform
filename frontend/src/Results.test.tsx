import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { TournamentResult } from "./api";
import { aPlayer, aTournament, fakeBackend } from "./testing/fakeBackend";

afterEach(() => {
  vi.unstubAllGlobals();
});

const IVAN = aPlayer({ id: 1, name: "Иван Петров" });
const MARIA = aPlayer({ id: 2, name: "Мария Иванова" });
const PETR = aPlayer({ id: 3, name: "Пётр Сидоров" });
const OLGA = aPlayer({ id: 4, name: "Ольга Кузнецова" });
const FINISHED = aTournament({ id: 5, name: "Пятничный турнир", status: "finished" });

function result(place: number, player: TournamentResult["player"], points: number) {
  return { place, player, points, reentries: 0, addons: 0 };
}

// Four players: 10, 4, 2 and 0 points by the league's formula.
const RESULTS = [
  result(1, MARIA, 10),
  result(2, PETR, 4),
  result(3, OLGA, 2),
  { ...result(4, IVAN, 0), reentries: 1 },
];

async function openResults(options: Parameters<typeof fakeBackend>[0] = {}) {
  const fetch = fakeBackend({
    loggedIn: true,
    tournaments: { upcoming: [], past: [FINISHED] },
    results: { 5: RESULTS },
    ...options,
  });
  const user = userEvent.setup();
  render(<App />);
  const row = await screen.findByRole("listitem", { name: "Пятничный турнир" });
  await user.click(within(row).getByRole("button", { name: "Результаты" }));
  await screen.findByRole("heading", { name: "Пятничный турнир" });
  return { user, fetch };
}

function results() {
  return screen.getByRole("list", { name: "Результаты" });
}

function standings() {
  return within(results())
    .getAllByRole("listitem")
    .map((row) => row.getAttribute("aria-label"));
}

describe("tournament results", () => {
  it("shows every player's place and points", async () => {
    await openResults();

    await screen.findByRole("list", { name: "Результаты" });
    expect(standings()).toEqual(["Мария Иванова", "Пётр Сидоров", "Ольга Кузнецова", "Иван Петров"]);
    const winner = within(results()).getByRole("listitem", { name: "Мария Иванова" });
    expect(winner).toHaveTextContent("1 место");
    expect(winner).toHaveTextContent("10 очков");
    const last = within(results()).getByRole("listitem", { name: "Иван Петров" });
    expect(last).toHaveTextContent("4 место");
    expect(last).toHaveTextContent("0 очков");
    expect(last).toHaveTextContent("re-entry: 1");
    expect(within(results()).getByRole("listitem", { name: "Пётр Сидоров" })).toHaveTextContent(
      "4 очка",
    );
  });

  it("corrects a place: the players in between move down and points are counted again", async () => {
    const { user, fetch } = await openResults();
    const ivan = await within(results()).findByRole("listitem", { name: "Иван Петров" });

    await user.click(within(ivan).getByRole("button", { name: "Исправить место" }));
    const form = screen.getByRole("form", { name: "Место игрока Иван Петров" });
    await user.clear(within(form).getByLabelText("Место"));
    await user.type(within(form).getByLabelText("Место"), "2");
    await user.click(within(form).getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Иван Петров: 2 место. Очки и рейтинг клуба пересчитаны.",
    );
    expect(standings()).toEqual(["Мария Иванова", "Иван Петров", "Пётр Сидоров", "Ольга Кузнецова"]);
    const ivanNow = within(results()).getByRole("listitem", { name: "Иван Петров" });
    expect(ivanNow).toHaveTextContent("2 место");
    expect(ivanNow).toHaveTextContent("4 очка");
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/clubs/7/tournaments/5/results/1",
      expect.objectContaining({ method: "PUT", body: JSON.stringify({ place: 2 }) }),
    );
  });

  it("leaves the places as they were when the correction is cancelled or fails", async () => {
    const { user } = await openResults({ down: ["PUT /api/clubs/7/tournaments/5/results/1"] });
    const ivan = await within(results()).findByRole("listitem", { name: "Иван Петров" });

    await user.click(within(ivan).getByRole("button", { name: "Исправить место" }));
    await user.click(screen.getByRole("button", { name: "Отмена" }));
    expect(screen.queryByRole("form")).not.toBeInTheDocument();

    await user.click(within(ivan).getByRole("button", { name: "Исправить место" }));
    const form = screen.getByRole("form", { name: "Место игрока Иван Петров" });
    await user.clear(within(form).getByLabelText("Место"));
    await user.type(within(form).getByLabelText("Место"), "1");
    await user.click(within(form).getByRole("button", { name: "Сохранить" }));

    expect(await within(form).findByRole("alert")).toHaveTextContent(
      "Не удалось связаться с сервером",
    );
    expect(standings()).toEqual(["Мария Иванова", "Пётр Сидоров", "Ольга Кузнецова", "Иван Петров"]);
  });

  it("says when a tournament has no results yet", async () => {
    await openResults({ results: {} });

    expect(
      await screen.findByText("Результаты появятся, когда турнир завершится."),
    ).toBeInTheDocument();
  });
});
