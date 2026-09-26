import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { aPlayer, fakeBackend } from "./testing/fakeBackend";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function openPlayers() {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Игроки" }));
  return user;
}

describe("club players", () => {
  it("adds a new player with consent to data processing", async () => {
    fakeBackend({ loggedIn: true });
    const user = await openPlayers();

    await user.type(await screen.findByLabelText("Имя"), "Иван Петров");
    await user.type(screen.getByLabelText("Телефон"), "8 913 555-12-34");
    await user.click(screen.getByLabelText(/Игрок согласен на обработку персональных данных/));
    await user.click(screen.getByRole("button", { name: "Добавить игрока" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Игрок Иван Петров добавлен");
    const list = screen.getByRole("list", { name: "Игроки клуба" });
    expect(within(list).getByRole("listitem", { name: "Иван Петров" })).toHaveTextContent(
      "+7 913 555-12-34",
    );
    expect(screen.getByLabelText("Имя")).toHaveValue("");
  });

  it("does not add a player without consent and says why", async () => {
    fakeBackend({ loggedIn: true });
    const user = await openPlayers();

    await user.type(await screen.findByLabelText("Имя"), "Иван Петров");
    await user.type(screen.getByLabelText("Телефон"), "8 913 555-12-34");
    await user.click(screen.getByRole("button", { name: "Добавить игрока" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Без согласия на обработку персональных данных игрока завести нельзя",
    );
    expect(screen.getByText("В клубе пока нет игроков")).toBeInTheDocument();
    expect(screen.getByLabelText("Имя")).toHaveValue("Иван Петров");
  });

  it("brings a player already known in the league into the club", async () => {
    fakeBackend({
      loggedIn: true,
      leaguePlayers: [aPlayer({ id: 3, name: "Иван Петров", phone: "+79135551234" })],
    });
    const user = await openPlayers();

    await user.type(await screen.findByLabelText("Имя"), "Ваня");
    await user.type(screen.getByLabelText("Телефон"), "+7 913 555 12 34");
    await user.click(screen.getByLabelText(/Игрок согласен/));
    await user.click(screen.getByRole("button", { name: "Добавить игрока" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Игрок Иван Петров уже есть в лиге и теперь добавлен в ваш клуб",
    );
    const list = screen.getByRole("list", { name: "Игроки клуба" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByRole("listitem", { name: "Иван Петров" })).toBeInTheDocument();
  });

  it("finds club players by name or phone", async () => {
    fakeBackend({
      loggedIn: true,
      players: [
        aPlayer({ id: 1, name: "Иван Петров", phone: "+79135551234" }),
        aPlayer({ id: 2, name: "Мария Иванова", phone: "+79131110002" }),
        aPlayer({ id: 3, name: "Сергей Никитин", phone: "+79131110003" }),
      ],
    });
    const user = await openPlayers();
    const list = await screen.findByRole("list", { name: "Игроки клуба" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);

    await user.type(screen.getByRole("searchbox", { name: "Поиск по имени или телефону" }), "иван");
    expect(await within(list).findByText("Мария Иванова")).toBeInTheDocument();
    await vi.waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(2));

    const search = screen.getByRole("searchbox", { name: "Поиск по имени или телефону" });
    await user.clear(search);
    await user.type(search, "Анна");
    expect(await screen.findByText("Никого не нашли")).toBeInTheDocument();
  });
});
