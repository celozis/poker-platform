import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { type BoardState, boardSocketUrl, fetchBoard } from "./api";
import {
  blinds,
  describe,
  formatTime,
  next,
  numberFormat,
  untilBreak,
  useCountdown,
} from "./blindClock";
import { startFormat } from "./dates";
import LeagueBrand from "./LeagueBrand";

type Shown = { board: BoardState; receivedAt: number };

// A lost connection is tried again soon, then less often while the server stays away.
const RECONNECT_DELAYS_MS = [1000, 2000, 5000, 10000];
// The code the server closes the connection with when it has no board with this secret code.
const BOARD_NOT_FOUND = 4404;

/**
 * The board as the server has it, kept up to date over a WebSocket: the server sends the board
 * on connecting and again after every change the admin makes. A lost connection is made again,
 * and the new one starts with the board as it is now. `offline` while there is no connection.
 */
function useBoard(token: string) {
  const [shown, setShown] = useState<Shown | null>(null);
  const [missing, setMissing] = useState(false);
  const [offline, setOffline] = useState(false);
  const latest = useRef(0);

  const show = useCallback((board: BoardState) => {
    // Any board replaces an older one still on its way.
    latest.current++;
    setShown({ board, receivedAt: Date.now() });
  }, []);

  const reload = useCallback(() => {
    const thisLoad = ++latest.current;
    fetchBoard(token)
      .then((board) => board && thisLoad === latest.current && setShown({ board, receivedAt: Date.now() }))
      .catch(() => {}); // The socket tells whether the server is there.
  }, [token]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    let stopped = false;

    function connect() {
      socket = new WebSocket(boardSocketUrl(token));
      socket.onmessage = (event: MessageEvent<string>) => {
        failures = 0;
        setOffline(false);
        show(JSON.parse(event.data));
      };
      socket.onclose = (event: CloseEvent) => {
        if (stopped) return;
        if (event.code === BOARD_NOT_FOUND) {
          setMissing(true);
          return;
        }
        setOffline(true);
        const delay = RECONNECT_DELAYS_MS[Math.min(failures++, RECONNECT_DELAYS_MS.length - 1)];
        retry = setTimeout(connect, delay);
      };
    }

    // The board is read first to tell a wrong link from a lost connection, which a WebSocket
    // cannot tell apart.
    fetchBoard(token)
      .then((board) => {
        if (stopped) return;
        if (board === null) setMissing(true);
        else {
          show(board);
          connect();
        }
      })
      .catch(() => {
        if (stopped) return;
        setOffline(true);
        connect();
      });

    return () => {
      stopped = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, [token, show]);

  return { shown, missing, offline, reload };
}

/** The hall board: a tournament on the club's TV, full screen, readable from across the room. */
export default function Board({ token }: { token: string }) {
  const { shown, missing, offline, reload } = useBoard(token);

  if (missing) return <Message>Табло не найдено</Message>;
  if (!shown) return <Message>{offline ? "Нет связи с сервером…" : "Загружаем табло…"}</Message>;

  const { board, receivedAt } = shown;
  const { club } = board;
  return (
    // Sizes follow both the width and the height of the screen, so that the board fills a TV of
    // any shape and never needs scrolling.
    <div
      className="flex h-screen flex-col gap-[2vh] overflow-hidden px-[2vw] py-[2vh] text-white"
      style={{ backgroundColor: club.primary_color }}
    >
      <header className="flex items-center gap-[2vw]">
        <img
          src={club.logo_url}
          alt={`Логотип: ${club.name}`}
          className="h-[min(6vw,10vh)] w-[min(6vw,10vh)] rounded-full bg-white p-[0.4vh]"
        />
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[length:min(3vw,5vh)] font-semibold leading-tight">
            {board.name}
          </h1>
          <p className="text-[length:min(1.8vw,3vh)] opacity-80">{club.name}</p>
        </div>
        <FullScreenButton />
        <LeagueBrand large className="text-white/90" />
      </header>
      <div className="h-[0.6vh] shrink-0" style={{ backgroundColor: club.accent_color }} />
      {offline && (
        <p
          role="status"
          className="rounded-lg bg-black/40 px-4 py-1 text-center text-[length:min(1.6vw,2.8vh)]"
        >
          Нет связи с сервером. Переподключаемся…
        </p>
      )}
      {board.clock ? (
        <Started board={board} receivedAt={receivedAt} onLevelOver={reload} />
      ) : (
        <Main>
          <NotLive board={board} />
        </Main>
      )}
    </div>
  );
}

function Message({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen items-center justify-center bg-slate-900 p-8 text-[length:min(3vw,5vh)] text-white">
      <p>{children}</p>
    </div>
  );
}

function Main({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-0 flex-1 flex-col items-center justify-center text-center">
      {children}
    </main>
  );
}

/** A started tournament: the clock while it is live, and the players and chips. */
function Started({
  board,
  receivedAt,
  onLevelOver,
}: {
  board: BoardState;
  receivedAt: number;
  onLevelOver: () => void;
}) {
  const secondsLeft = useCountdown(board.structure, board.clock!, receivedAt, onLevelOver);
  const live = board.status === "running" || board.status === "paused";
  return (
    <>
      <Main>{live ? <ClockFace board={board} secondsLeft={secondsLeft} /> : <NotLive board={board} />}</Main>
      <Stats board={board} secondsLeft={live ? secondsLeft : null} />
    </>
  );
}

function ClockFace({ board, secondsLeft }: { board: BoardState; secondsLeft: number }) {
  const clock = board.clock!;
  const { structure } = board;
  const item = structure[clock.item];
  return (
    <>
      <div className="flex items-center gap-[2vw] text-[length:min(3.2vw,5.5vh)] font-semibold leading-tight uppercase tracking-wide">
        <p className="opacity-90">{describe(structure, clock.item).name}</p>
        {!clock.running && (
          <p
            className="rounded-full px-[2vw] text-slate-900"
            style={{ backgroundColor: board.club.accent_color }}
          >
            Пауза
          </p>
        )}
      </div>
      <p
        role="timer"
        className="text-[length:min(19vw,25vh)] font-bold leading-none tabular-nums"
        style={{ color: clock.running ? undefined : board.club.accent_color }}
      >
        {formatTime(secondsLeft)}
      </p>
      {item.kind === "level" && (
        <>
          <p className="mt-[1vh] text-[length:min(7.5vw,11vh)] font-bold leading-none tabular-nums">
            {blinds(item)}
          </p>
          {item.ante > 0 && (
            <p className="mt-[1vh] text-[length:min(3.2vw,5.5vh)] font-semibold leading-tight">
              Анте {numberFormat.format(item.ante)}
            </p>
          )}
        </>
      )}
      <p className="mt-[1.5vh] text-[length:min(2.2vw,3.6vh)] opacity-80">
        {next(structure, clock.item)}
      </p>
    </>
  );
}

/** Before the start, and once the tournament is over or cancelled. */
function NotLive({ board }: { board: BoardState }) {
  const big = "text-[length:min(7vw,12vh)] font-bold";
  if (board.status === "finished") return <p className={big}>Турнир завершён</p>;
  if (board.status === "cancelled") return <p className={big}>Турнир отменён</p>;
  const first = board.structure.find((item) => item.kind === "level");
  return (
    <>
      <p className="text-[length:min(3vw,5vh)] opacity-80">Начало</p>
      <p className={`${big} leading-tight`}>{startFormat.format(new Date(board.starts_at))}</p>
      {first && (
        <p className="mt-[3vh] text-[length:min(4vw,7vh)]">Уровень 1 · {blinds(first)}</p>
      )}
      <p className="text-[length:min(3vw,5vh)] opacity-80">
        Стартовый стек {numberFormat.format(board.starting_stack)}
      </p>
    </>
  );
}

/** `secondsLeft` of the item being played; null once the tournament is over. */
function Stats({ board, secondsLeft }: { board: BoardState; secondsLeft: number | null }) {
  const toBreak =
    secondsLeft === null ? null : untilBreak(board.structure, board.clock!.item, secondsLeft);
  const onBreak = board.structure[board.clock!.item].kind === "break";
  return (
    <footer className="grid shrink-0 grid-cols-2 gap-[1.5vw] lg:grid-cols-4">
      <Tile label="Игроков">
        {board.players_left}
        <span className="text-[length:min(1.8vw,3vh)] opacity-70"> из {board.players}</span>
      </Tile>
      <Tile label="Re-entry">{board.reentries}</Tile>
      <Tile label="Средний стек">
        {board.average_stack === null ? "—" : numberFormat.format(board.average_stack)}
      </Tile>
      <Tile label={onBreak ? "Следующий перерыв через" : "Перерыв через"}>
        {secondsLeft === null ? (
          "—"
        ) : toBreak === null ? (
          <span className="text-[length:min(1.8vw,3vh)]">Перерывов больше нет</span>
        ) : (
          <span className="tabular-nums">{formatTime(toBreak)}</span>
        )}
      </Tile>
    </footer>
  );
}

function Tile({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={label} className="rounded-2xl bg-black/25 px-[1.5vw] py-[1.2vh]">
      <p className="text-[length:min(1.4vw,2.4vh)] uppercase tracking-wide opacity-80">{label}</p>
      <p className="whitespace-nowrap text-[length:min(3.4vw,6vh)] font-bold leading-tight tabular-nums">
        {children}
      </p>
    </div>
  );
}

/** A TV browser opens the page in a window; one click on it fills the screen. */
function FullScreenButton() {
  const [fullScreen, setFullScreen] = useState(() => Boolean(document.fullscreenElement));
  useEffect(() => {
    const update = () => setFullScreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);
  if (fullScreen || !document.documentElement.requestFullscreen) return null;
  return (
    <button
      type="button"
      onClick={() => document.documentElement.requestFullscreen().catch(() => {})}
      className="rounded-lg border border-white/50 px-[1vw] py-[0.5vh] text-[length:min(1.4vw,2.4vh)]"
    >
      Во весь экран
    </button>
  );
}
