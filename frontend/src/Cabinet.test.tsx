import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import Cabinet from "./Cabinet";
import { aCabinet, fakeBackend, ME, VALID_CODE } from "./testing/fakeBackend";

afterEach(() => {
  vi.unstubAllGlobals();
});

const ENISEY = {
  id: 8,
  name: "Покер-клуб «Енисей»",
  logo_url: "/logos/enisey.svg",
  primary_color: "#7A1F1F",
  accent_color: "#D4AF37",
};

describe("player cabinet", () => {
  it("logs the player in with the code and shows their profile", async () => {
    fakeBackend({
      cabinet: aCabinet({
        player: { name: "Мария Иванова", phone: "+79135551234", telegram_linked: true },
        clubs: [
          { club: ME.club, rating: null, schedule: [] },
          { club: ENISEY, rating: null, schedule: [] },
        ],
      }),
    });
    const user = userEvent.setup();
    render(<Cabinet />);

    expect(
      await screen.findByRole("heading", { name: "Личный кабинет игрока" }),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Номер телефона"), "+79135551234");
    await user.click(screen.getByRole("button", { name: "Получить код" }));
    await user.type(await screen.findByLabelText("Код из SMS"), VALID_CODE);
    await user.click(screen.getByRole("button", { name: "Войти" }));

    const profile = await screen.findByRole("region", { name: "Профиль" });
    expect(within(profile).getByText("Мария Иванова")).toBeInTheDocument();
    expect(within(profile).getByText("+7 913 555-12-34")).toBeInTheDocument();
    expect(
      within(profile).getByText("Покер-клуб «Обь», Покер-клуб «Енисей»"),
    ).toBeInTheDocument();
    expect(within(profile).getByText("привязан")).toBeInTheDocument();
  });

  it("shows the player's position and points in each of their clubs' ratings this season", async () => {
    fakeBackend({
      playerLoggedIn: true,
      cabinet: aCabinet({
        clubs: [
          { club: ME.club, rating: { position: 2, points: 6, tournaments: 2 }, schedule: [] },
          { club: ENISEY, rating: null, schedule: [] },
        ],
      }),
    });
    render(<Cabinet />);

    const rating = await screen.findByRole("region", { name: "Рейтинг" });
    expect(within(rating).getByText("2-е полугодие 2026")).toBeInTheDocument();
    const [ob, enisey] = within(rating).getAllByRole("listitem");
    expect(ob).toHaveTextContent("Покер-клуб «Обь»");
    expect(ob).toHaveTextContent("2-е место");
    expect(ob).toHaveTextContent("6 очков · 2 турнира");
    expect(enisey).toHaveTextContent("Покер-клуб «Енисей»");
    expect(enisey).toHaveTextContent("Пока нет в рейтинге: сыграйте турнир клуба в этом сезоне");
  });

  it("lists each club's coming tournaments, marking those going on and those signed up for", async () => {
    fakeBackend({
      playerLoggedIn: true,
      cabinet: aCabinet({
        clubs: [
          {
            club: ME.club,
            rating: null,
            schedule: [
              {
                name: "Вечерний турнир",
                starts_at: "2026-09-26T12:00:00Z",
                buy_in: 2000,
                going_on: true,
                registered: true,
              },
              {
                name: "Субботний турнир",
                starts_at: "2026-10-03T12:00:00Z",
                buy_in: 2500,
                going_on: false,
                registered: false,
              },
            ],
          },
          { club: ENISEY, rating: null, schedule: [] },
        ],
      }),
    });
    render(<Cabinet />);

    const coming = await screen.findByRole("region", { name: "Ближайшие турниры" });
    const [evening, saturday] = within(
      within(coming).getByRole("list", { name: "Покер-клуб «Обь»" }),
    ).getAllByRole("listitem");
    expect(evening).toHaveTextContent("Вечерний турнир");
    expect(evening).toHaveTextContent("26 сентября");
    expect(evening).toHaveTextContent("19:00");
    expect(evening).toHaveTextContent("бай-ин 2 000 ₽");
    expect(evening).toHaveTextContent("Идёт");
    expect(evening).toHaveTextContent("Вы записаны");
    expect(saturday).toHaveTextContent("Субботний турнир");
    expect(saturday).toHaveTextContent("3 октября");
    expect(saturday).toHaveTextContent("бай-ин 2 500 ₽");
    expect(saturday).not.toHaveTextContent("Идёт");
    expect(saturday).not.toHaveTextContent("Вы записаны");
    const enisey = within(coming).getByRole("heading", { name: "Покер-клуб «Енисей»" });
    expect(enisey.nextElementSibling).toHaveTextContent("Запланированных турниров пока нет");
  });

  it("shows the tournaments the player has played, the latest first", async () => {
    fakeBackend({
      playerLoggedIn: true,
      cabinet: aCabinet({
        history: [
          {
            starts_at: "2026-09-26T13:00:00Z",
            tournament: "Енисей Open",
            club: "Покер-клуб «Енисей»",
            place: 1,
            players: 2,
            points: 4,
            reentries: 0,
            addons: 0,
          },
          {
            starts_at: "2026-09-19T12:00:00Z",
            tournament: "Пятничный турнир",
            club: "Покер-клуб «Обь»",
            place: 3,
            players: 9,
            points: 7,
            reentries: 1,
            addons: 2,
          },
        ],
      }),
    });
    render(<Cabinet />);

    const history = await screen.findByRole("region", { name: "История турниров" });
    const [latest, earlier] = within(history).getAllByRole("listitem");
    expect(latest).toHaveTextContent("26 сентября 2026");
    expect(latest).toHaveTextContent("Енисей Open");
    expect(latest).toHaveTextContent("Покер-клуб «Енисей»");
    expect(latest).toHaveTextContent("1-е место из 2");
    expect(latest).toHaveTextContent("4 очка");
    expect(latest).not.toHaveTextContent("re-entry");
    expect(earlier).toHaveTextContent("19 сентября 2026");
    expect(earlier).toHaveTextContent("Пятничный турнир");
    expect(earlier).toHaveTextContent("Покер-клуб «Обь»");
    expect(earlier).toHaveTextContent("3-е место из 9");
    expect(earlier).toHaveTextContent("7 очков");
    expect(earlier).toHaveTextContent("re-entry: 1, add-on: 2");
  });

  it("says when the player has not played a tournament yet", async () => {
    fakeBackend({ playerLoggedIn: true, cabinet: aCabinet({ history: [] }) });
    render(<Cabinet />);

    const history = await screen.findByRole("region", { name: "История турниров" });
    expect(history).toHaveTextContent("Вы ещё не сыграли ни одного турнира");
  });

  it("logs the player out back to the login form", async () => {
    const fetch = fakeBackend({ playerLoggedIn: true });
    const user = userEvent.setup();
    render(<Cabinet />);

    await user.click(await screen.findByRole("button", { name: "Выйти" }));

    expect(await screen.findByLabelText("Номер телефона")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/cabinet/logout",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("tells a player on no club's list yet where to choose their club", async () => {
    fakeBackend({ playerLoggedIn: true, cabinet: aCabinet({ clubs: [] }) });
    render(<Cabinet />);

    const profile = await screen.findByRole("region", { name: "Профиль" });
    expect(profile).toHaveTextContent("пока нет: выберите клуб в Telegram-боте лиги");
    for (const name of ["Рейтинг", "Ближайшие турниры"]) {
      expect(screen.getByRole("region", { name })).toHaveTextContent(
        "Вы пока не в списке ни одного клуба",
      );
    }
  });
});
