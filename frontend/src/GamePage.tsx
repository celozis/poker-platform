import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  actOnPlayer,
  type Club,
  fetchGame,
  type FinishedPlayer,
  type GameAction,
  type GameState,
  movePlayer,
  type PlayerAction,
  registerPlayer,
  RejectedError,
  runGame,
  type SeatedPlayer,
  type StructureItem,
  type Tournament,
} from "./api";
import { startFormat } from "./dates";
import { SERVER_UNREACHABLE, smallButton } from "./forms";
import { SignUp } from "./RegistrationsPage";
import { STATUS_NAMES } from "./tournamentStatus";

const numberFormat = new Intl.NumberFormat("ru-RU");

type Loaded = { game: GameState; receivedAt: number };

/** Running one tournament: start, the blind clock, the tables, knock-outs and the final table. */
export default function GamePage({
  club,
  tournament,
  onBack,
}: {
  club: Club;
  tournament: Tournament;
  onBack: () => void;
}) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [error, setError] = useState("");
  const latestLoad = useRef(0);
  // One action at a time: a second click while the first is on its way is ignored.
  const acting = useRef(false);

  const show = useCallback((game: GameState) => {
    // Any answer replaces an older one still on its way.
    latestLoad.current++;
    setLoaded({ game, receivedAt: Date.now() });
  }, []);

  const load = useCallback(() => {
    const thisLoad = ++latestLoad.current;
    fetchGame(club.id, tournament.id)
      .then((game) => thisLoad === latestLoad.current && setLoaded({ game, receivedAt: Date.now() }))
      .catch(() => thisLoad === latestLoad.current && setLoadFailed(true));
  }, [club.id, tournament.id]);

  useEffect(load, [load]);

  /** Runs an action and shows the game the server answers with; a refusal is shown on top. */
  async function change(action: () => Promise<GameState>) {
    if (acting.current) return;
    acting.current = true;
    setError("");
    try {
      show(await action());
    } catch (failure) {
      setError(failure instanceof RejectedError ? failure.messages.join("\n") : SERVER_UNREACHABLE);
    } finally {
      acting.current = false;
    }
  }

  const game = loaded?.game;
  const run = (action: GameAction) => change(() => runGame(club.id, tournament.id, action));
  const act = (playerId: number, action: PlayerAction) =>
    change(() => actOnPlayer(club.id, tournament.id, playerId, action));
  const live = game?.status === "running" || game?.status === "paused";

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{tournament.name}</h2>
            <p className="text-sm text-slate-600">
              {startFormat.format(new Date(tournament.starts_at))}
              {game && (
                <span className="ml-2 rounded-full bg-slate-100 px-3 py-0.5 text-slate-700">
                  {STATUS_NAMES[game.status]}
                </span>
              )}
            </p>
          </div>
          <button
            type="button"
            onClick={onBack}
            className="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-700"
          >
            Назад к списку
          </button>
        </div>
      </div>

      {error && (
        <p role="alert" className="whitespace-pre-line rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}
      {!loaded && !loadFailed && <p className="text-slate-600">Загружаем турнир…</p>}
      {loadFailed && (
        <p role="alert" className="text-red-700">
          Не удалось загрузить турнир. Обновите страницу.
        </p>
      )}

      {game?.status === "scheduled" && (
        <StartPanel game={game} primaryColor={club.primary_color} onStart={() => run("start")} />
      )}
      {game?.status === "cancelled" && (
        <p className="rounded-2xl bg-white p-4 text-sm text-slate-600 shadow-sm">Турнир отменён.</p>
      )}
      {loaded && live && loaded.game.clock && (
        <ClockPanel
          tournament={tournament}
          game={loaded.game}
          receivedAt={loaded.receivedAt}
          onAction={run}
          onLevelOver={load}
        />
      )}
      {game && live && game.suggested_move && (
        <MoveSuggestion
          game={game}
          onMove={() => {
            const move = game.suggested_move!;
            change(() =>
              movePlayer(club.id, tournament.id, move.player.id, {
                table: move.to_table,
                seat: move.to_seat,
              }),
            );
          }}
        />
      )}
      {game && live && <Tables game={game} onAct={act} />}
      {game && live && game.windows.late_registration && (
        <SignUp
          club={club}
          title="Поздняя регистрация"
          registerLabel="Посадить"
          addLabel="Добавить и посадить"
          registeredIds={
            new Set(
              [...game.in_game, ...game.out, ...game.waiting].map((entry) => entry.player.id),
            )
          }
          register={(playerId) =>
            change(async () => {
              await registerPlayer(club.id, tournament.id, playerId);
              return actOnPlayer(club.id, tournament.id, playerId, "seat");
            })
          }
        >
          <Waiting game={game} onSeat={(playerId) => act(playerId, "seat")} />
        </SignUp>
      )}
      {game?.status === "finished" && (
        <p className="rounded-2xl bg-white p-4 font-medium text-slate-900 shadow-sm">
          Турнир завершён
        </p>
      )}
      {game && game.out.length > 0 && (
        <Finished game={game} onReenter={(playerId) => act(playerId, "reentry")} />
      )}
    </div>
  );
}

function StartPanel({
  game,
  primaryColor,
  onStart,
}: {
  game: GameState;
  primaryColor: string;
  onStart: () => void;
}) {
  const arrived = game.waiting.filter((r) => r.status === "checked_in").length;
  return (
    <section className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-white p-6 shadow-sm">
      <div>
        <p className="font-medium text-slate-900">
          Пришли: {arrived} из {game.waiting.length}
        </p>
        <p className="text-sm text-slate-600">
          При старте пришедших рассадят по столам на {game.seats_per_table} мест. Опоздавших
          сажают через позднюю регистрацию.
        </p>
      </div>
      <button
        type="button"
        onClick={onStart}
        className="rounded-lg px-4 py-2 font-medium text-white"
        style={{ backgroundColor: primaryColor }}
      >
        Начать турнир
      </button>
    </section>
  );
}

/** "Уровень 2" and "200 / 400, анте 50", or "Перерыв" with no blinds. */
function describe(structure: StructureItem[], index: number): { name: string; blinds: string } {
  const item = structure[index];
  if (item.kind === "break") return { name: "Перерыв", blinds: "" };
  const level = structure.slice(0, index + 1).filter((i) => i.kind === "level").length;
  const blinds = `${numberFormat.format(item.small_blind)} / ${numberFormat.format(item.big_blind)}`;
  return {
    name: `Уровень ${level}`,
    blinds: item.ante > 0 ? `${blinds}, анте ${numberFormat.format(item.ante)}` : blinds,
  };
}

function next(structure: StructureItem[], index: number): string {
  if (index + 1 >= structure.length) return "Последний уровень структуры";
  const item = structure[index + 1];
  if (item.kind === "break") return `Дальше: перерыв ${item.duration_minutes} мин`;
  const { name, blinds } = describe(structure, index + 1);
  return `Дальше: ${name.toLowerCase()} · ${blinds}`;
}

const pad = (value: number) => String(value).padStart(2, "0");

function formatTime(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const clock = `${pad(minutes)}:${pad(seconds % 60)}`;
  return hours > 0 ? `${hours}:${clock}` : clock;
}

/** Seconds left on the level, counted down in the browser from what the server said. */
function useSecondsLeft(game: GameState, receivedAt: number): number {
  const [now, setNow] = useState(() => Date.now());
  const clock = game.clock!;
  useEffect(() => {
    setNow(Date.now());
    if (!clock.running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [clock.running, receivedAt]);
  if (!clock.running) return clock.seconds_left;
  return Math.max(0, clock.seconds_left - Math.floor((now - receivedAt) / 1000));
}

function ClockPanel({
  tournament,
  game,
  receivedAt,
  onAction,
  onLevelOver,
}: {
  tournament: Tournament;
  game: GameState;
  receivedAt: number;
  onAction: (action: GameAction) => void;
  /** The level's time is up: the server knows what comes next. */
  onLevelOver: () => void;
}) {
  const clock = game.clock!;
  const { structure } = tournament;
  const secondsLeft = useSecondsLeft(game, receivedAt);
  const headingId = useId();
  const isLast = clock.item >= structure.length - 1;
  const levelOver = clock.running && clock.seconds_left > 0 && secondsLeft === 0 && !isLast;

  useEffect(() => {
    if (levelOver) onLevelOver();
  }, [levelOver, onLevelOver]);

  const { name, blinds } = describe(structure, clock.item);
  const hints = [
    game.windows.reentry && `Re-entry открыт до уровня ${tournament.reentry_until_level}`,
    game.windows.addon && "Сейчас можно взять add-on",
    game.windows.late_registration &&
      `Поздняя регистрация открыта до уровня ${tournament.late_registration_until_level}`,
  ].filter(Boolean);

  return (
    <section aria-labelledby={headingId} className="rounded-2xl bg-white p-6 shadow-sm">
      <h3 id={headingId} className="sr-only">
        Блайнды
      </h3>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium uppercase tracking-wide text-slate-500">{name}</p>
          {blinds && <p className="text-3xl font-semibold text-slate-900">{blinds}</p>}
          <p className="mt-1 text-sm text-slate-600">{next(structure, clock.item)}</p>
        </div>
        <div className="text-right">
          <p className="font-mono text-5xl font-semibold tabular-nums text-slate-900">
            {formatTime(secondsLeft)}
          </p>
          {!clock.running && <p className="text-sm font-medium text-amber-700">на паузе</p>}
        </div>
      </div>
      {hints.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-2 text-sm">
          {hints.map((hint) => (
            <li key={String(hint)} className="rounded-full bg-emerald-50 px-3 py-1 text-emerald-800">
              {hint}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <button type="button" onClick={() => onAction("previous-level")} className={smallButton}>
          Предыдущий уровень
        </button>
        {clock.running ? (
          <button type="button" onClick={() => onAction("pause")} className={smallButton}>
            Пауза
          </button>
        ) : (
          <button type="button" onClick={() => onAction("resume")} className={smallButton}>
            Продолжить
          </button>
        )}
        <button type="button" onClick={() => onAction("next-level")} className={smallButton}>
          Следующий уровень
        </button>
      </div>
    </section>
  );
}

function MoveSuggestion({ game, onMove }: { game: GameState; onMove: () => void }) {
  const move = game.suggested_move!;
  return (
    <div
      role="status"
      aria-label="Пересадка"
      className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-amber-50 p-4 text-amber-900 shadow-sm"
    >
      <p>
        Столы неровные, пересадите: {move.player.name}: стол {move.from_table}, место{" "}
        {move.from_seat} → стол {move.to_table}, место {move.to_seat}
      </p>
      <button type="button" onClick={onMove} className={smallButton}>
        Пересадить
      </button>
    </div>
  );
}

function entries(player: { reentries: number; addons: number }): string {
  return [
    player.reentries > 0 && `re-entry: ${player.reentries}`,
    player.addons > 0 && `add-on: ${player.addons}`,
  ]
    .filter(Boolean)
    .join(", ");
}

function Tables({
  game,
  onAct,
}: {
  game: GameState;
  onAct: (playerId: number, action: PlayerAction) => void;
}) {
  const tables = [...new Set(game.in_game.map((s) => s.table))].sort((a, b) => a - b);
  // One table left of a tournament that needed more: the final table.
  const final = tables.length === 1 && game.in_game.length + game.out.length > game.seats_per_table;

  function knockOut(seated: SeatedPlayer) {
    if (window.confirm(`Игрок ${seated.player.name} выбыл?`)) onAct(seated.player.id, "knock-out");
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      {tables.map((table) => (
        <TableCard
          key={table}
          title={final ? "Финальный стол" : `Стол ${table}`}
          seats={game.in_game.filter((s) => s.table === table)}
          canAddon={(s) => game.windows.addon && !s.addon_this_entry}
          onKnockOut={knockOut}
          onAddon={(s) => onAct(s.player.id, "addon")}
        />
      ))}
    </div>
  );
}

function TableCard({
  title,
  seats,
  canAddon,
  onKnockOut,
  onAddon,
}: {
  title: string;
  seats: SeatedPlayer[];
  canAddon: (seated: SeatedPlayer) => boolean;
  onKnockOut: (seated: SeatedPlayer) => void;
  onAddon: (seated: SeatedPlayer) => void;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="rounded-2xl bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h3 id={headingId} className="font-semibold text-slate-900">
          {title}
        </h3>
        <p className="text-sm text-slate-500">Игроков: {seats.length}</p>
      </div>
      <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200">
        {seats.map((seated) => (
          <li
            key={seated.player.id}
            aria-label={seated.player.name}
            className="flex flex-wrap items-center gap-x-3 gap-y-2 p-2"
          >
            <span className="w-16 text-sm text-slate-500">Место {seated.seat}</span>
            <div className="min-w-32 flex-1">
              <p className="font-medium text-slate-900">{seated.player.name}</p>
              {entries(seated) && <p className="text-xs text-slate-500">{entries(seated)}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              {canAddon(seated) && (
                <button type="button" onClick={() => onAddon(seated)} className={smallButton}>
                  Add-on
                </button>
              )}
              <button
                type="button"
                onClick={() => onKnockOut(seated)}
                className="rounded-lg border border-red-200 px-3 py-1 text-sm text-red-700"
              >
                Отметить выбывание
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Waiting({ game, onSeat }: { game: GameState; onSeat: (playerId: number) => void }) {
  if (game.waiting.length === 0) return null;
  return (
    <ul
      aria-label="Ждут посадки"
      className="mb-4 divide-y divide-slate-200 rounded-xl border border-slate-200"
    >
      {game.waiting.map(({ player }) => (
        <li key={player.id} aria-label={player.name} className="flex items-center gap-3 p-2">
          <p className="flex-1 font-medium text-slate-900">{player.name}</p>
          <button type="button" onClick={() => onSeat(player.id)} className={smallButton}>
            Посадить
          </button>
        </li>
      ))}
    </ul>
  );
}

function Finished({
  game,
  onReenter,
}: {
  game: GameState;
  onReenter: (playerId: number) => void;
}) {
  const finished = game.status === "finished";
  const title = finished ? "Итоги" : "Выбывшие";
  return (
    <section className="rounded-2xl bg-white p-6 shadow-sm">
      <h3 className="mb-3 text-lg font-semibold text-slate-900">{title}</h3>
      <ul aria-label={title} className="divide-y divide-slate-200 rounded-xl border border-slate-200">
        {game.out.map((player: FinishedPlayer) => (
          <li
            key={player.player.id}
            aria-label={player.player.name}
            className="flex flex-wrap items-center gap-x-3 gap-y-2 p-2"
          >
            <span className="w-20 font-medium text-slate-900">{player.place} место</span>
            <div className="min-w-32 flex-1">
              <p className="text-slate-900">{player.player.name}</p>
              {entries(player) && <p className="text-xs text-slate-500">{entries(player)}</p>}
            </div>
            {!finished && game.windows.reentry && (
              <button
                type="button"
                onClick={() => onReenter(player.player.id)}
                className={smallButton}
              >
                Re-entry
              </button>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
