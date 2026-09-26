import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { aPlayer, aTournament, fakeBackend } from "./testing/fakeBackend";

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

  it("checks in an arrival and undoes a mistaken check-in", async () => {
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
    const user = await openRegistrations();
    const ivan = await within(registered()).findByRole("listitem", { name: "Иван Петров" });

    await user.click(within(ivan).getByRole("button", { name: "Отметить приход" }));
    expect(await within(ivan).findByText("Пришёл")).toBeInTheDocument();
    expect(screen.getByText("Зарегистрировано: 2, пришли: 1")).toBeInTheDocument();

    await user.click(within(ivan).getByRole("button", { name: "Отменить приход" }));
    expect(await within(ivan).findByText("Зарегистрирован")).toBeInTheDocument();
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
});
