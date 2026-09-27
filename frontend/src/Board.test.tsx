import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { BoardState } from "./api";
import Board from "./Board";
import { ME, TEMPLATES, fakeBackend } from "./testing/fakeBackend";
import { fakeWebSockets } from "./testing/fakeWebSocket";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const TOKEN = "3f9a1c2b7d4e";

/** A board of ME's club: level 1 of the standard structure is running, 20 players have played. */
function aBoard(overrides: Partial<BoardState> = {}): BoardState {
  return {
    club: ME.club,
    name: "Пятничный турнир",
    starts_at: "2026-10-02T12:00:00Z",
    status: "running",
    starting_stack: 20000,
    structure: TEMPLATES[0].structure,
    clock: { running: true, item: 0, seconds_left: 754.3 },
    players_left: 17,
    players: 20,
    reentries: 3,
    average_stack: 27059,
    ...overrides,
  };
}

async function openBoard(board: BoardState | null = aBoard()) {
  const sockets = fakeWebSockets();
  const fetch = fakeBackend({ boards: board ? { [TOKEN]: board } : {} });
  render(<Board token={TOKEN} />);
  return { sockets, fetch };
}

function tile(name: string) {
  return screen.getByRole("group", { name });
}

describe("the hall board", () => {
  it("shows the level, the countdown, what comes next and the players", async () => {
    // The countdown runs on Date.now(): stopped, so that a slow run does not tick it down.
    vi.useFakeTimers({ toFake: ["Date"] });
    await openBoard();

    expect(await screen.findByRole("heading", { name: "Пятничный турнир" })).toBeInTheDocument();
    expect(screen.getByText("Покер-клуб «Обь»")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Логотип: Покер-клуб «Обь»" })).toBeInTheDocument();
    expect(screen.getByText("Сибирская лига покера")).toBeInTheDocument();
    expect(screen.getByText("Уровень 1")).toBeInTheDocument();
    expect(screen.getByText("100 / 200")).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveTextContent("12:35");
    expect(screen.getByText("Дальше: уровень 2 · 200 / 400")).toBeInTheDocument();
    expect(tile("Игроков")).toHaveTextContent("17 из 20");
    expect(tile("Re-entry")).toHaveTextContent("3");
    expect(tile("Средний стек")).toHaveTextContent("27 059");
    // 12:35 of level 1 and 20 minutes of level 2.
    expect(tile("Перерыв через")).toHaveTextContent("32:35");
  });

  it("shows the ante once there is one", async () => {
    await openBoard(aBoard({ clock: { running: true, item: 3, seconds_left: 600 } }));

    expect(await screen.findByText("Уровень 3")).toBeInTheDocument();
    expect(screen.getByText("300 / 600")).toBeInTheDocument();
    expect(screen.getByText("Анте 75")).toBeInTheDocument();
    expect(tile("Перерыв через")).toHaveTextContent("Перерывов больше нет");
  });

  it("counts to the break after the one being played", async () => {
    await openBoard(aBoard({ clock: { running: true, item: 2, seconds_left: 300 } }));

    expect(await screen.findByText("Перерыв")).toBeInTheDocument();
    // No break is left after this one in the standard structure.
    expect(tile("Следующий перерыв через")).toHaveTextContent("Перерывов больше нет");
  });

  it("says so when the link leads nowhere", async () => {
    const { sockets } = await openBoard(null);

    expect(await screen.findByText("Табло не найдено")).toBeInTheDocument();
    expect(sockets).toHaveLength(0);
  });

  it("connects to the tournament's updates once it has the board", async () => {
    const { sockets } = await openBoard();

    await screen.findByRole("timer");
    expect(sockets.map((socket) => socket.url)).toEqual([`ws://localhost:3000/api/board/${TOKEN}/ws`]);
  });

  it("shows a pause and a knock-out as soon as the server sends them", async () => {
    const { sockets } = await openBoard();
    await screen.findByRole("timer");
    act(() => sockets[0].open(aBoard()));

    act(() =>
      sockets[0].send(aBoard({ status: "paused", clock: { running: false, item: 0, seconds_left: 700 } })),
    );
    expect(screen.getByText("Пауза")).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveTextContent("11:40");

    act(() =>
      sockets[0].send(
        aBoard({
          status: "paused",
          clock: { running: false, item: 0, seconds_left: 700 },
          players_left: 16,
          average_stack: 28750,
        }),
      ),
    );
    expect(tile("Игроков")).toHaveTextContent("16 из 20");
    expect(tile("Средний стек")).toHaveTextContent("28 750");
  });

  it("counts down while the clock runs and stands still on a pause", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { sockets } = await openBoard(aBoard({ clock: { running: true, item: 0, seconds_left: 65 } }));
    expect(await screen.findByRole("timer")).toHaveTextContent("01:05");

    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(screen.getByRole("timer")).toHaveTextContent("01:02");
    expect(tile("Перерыв через")).toHaveTextContent("21:02");

    act(() => sockets[0].open(aBoard({ status: "paused", clock: { running: false, item: 0, seconds_left: 61.5 } })));
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(screen.getByRole("timer")).toHaveTextContent("01:02");
  });

  it("asks the server what comes next when the level's time is up", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const board = aBoard({ clock: { running: true, item: 0, seconds_left: 2 } });
    const { fetch } = await openBoard(board);
    await screen.findByRole("timer");
    // By then the server has moved on to level 2 by itself.
    board.clock = { running: true, item: 1, seconds_left: 1199.5 };

    await act(() => vi.advanceTimersByTimeAsync(2500));

    const boardCalls = fetch.mock.calls.filter(([url]) => url === `/api/board/${TOKEN}`);
    expect(boardCalls).toHaveLength(2);
    expect(screen.getByText("Уровень 2")).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveTextContent("20:00");
  });

  it("asks again when the question at the level's end goes unanswered", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const board = aBoard({ clock: { running: true, item: 0, seconds_left: 2 } });
    const { fetch } = await openBoard(board);
    await screen.findByRole("timer");
    board.clock = { running: true, item: 1, seconds_left: 1197.5 };
    fetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await act(() => vi.advanceTimersByTimeAsync(2500));
    expect(screen.getByRole("timer")).toHaveTextContent("00:00");
    await act(() => vi.advanceTimersByTimeAsync(3000));

    expect(screen.getByText("Уровень 2")).toBeInTheDocument();
  });

  it("reconnects by itself when the connection is lost and shows the board as it is now", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { sockets } = await openBoard();
    await screen.findByRole("timer");
    act(() => sockets[0].open(aBoard()));

    act(() => sockets[0].drop());
    expect(screen.getByRole("status")).toHaveTextContent("Нет связи с сервером. Переподключаемся…");
    // The clock goes on counting while the board is off line.
    expect(screen.getByRole("timer")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(sockets).toHaveLength(2);
    act(() => sockets[1].open(aBoard({ clock: { running: true, item: 1, seconds_left: 1200 } })));

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.getByText("Уровень 2")).toBeInTheDocument();
    expect(screen.getByRole("timer")).toHaveTextContent("20:00");
  });

  it("keeps trying, less often, while the server stays away", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const { sockets } = await openBoard();
    await screen.findByRole("timer");

    act(() => sockets[0].drop());
    await act(() => vi.advanceTimersByTimeAsync(1000));
    act(() => sockets[1].drop());
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(sockets).toHaveLength(2);
    await act(() => vi.advanceTimersByTimeAsync(1000));
    expect(sockets).toHaveLength(3);
  });

  it("fills the screen at a click", async () => {
    // jsdom has no full screen.
    const requestFullscreen = vi.fn(() => Promise.resolve());
    Object.defineProperty(document.documentElement, "requestFullscreen", {
      value: requestFullscreen,
      configurable: true,
    });
    await openBoard();

    await userEvent.click(await screen.findByRole("button", { name: "Во весь экран" }));

    expect(requestFullscreen).toHaveBeenCalledTimes(1);
    delete (document.documentElement as Partial<HTMLElement>).requestFullscreen;
  });

  it("says the link leads nowhere when the server refuses the connection", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const sockets = fakeWebSockets();
    // The page was opened while the server was away, so only the WebSocket can tell.
    fakeBackend({ down: [`GET /api/board/${TOKEN}`] });
    render(<Board token={TOKEN} />);
    await vi.waitFor(() => expect(sockets).toHaveLength(1));

    act(() => sockets[0].refuse());

    expect(screen.getByText("Табло не найдено")).toBeInTheDocument();
    await act(() => vi.advanceTimersByTimeAsync(15000));
    expect(sockets).toHaveLength(1);
  });
});
