import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  actOnPlayer,
  type Club,
  fetchGame,
  type FinishedPlayer,
  type GameAction,
  type GameState,
  movePlayer,
  type Player,
  type PlayerAction,
  type Registration,
  registerPlayer,
  RejectedError,
  runGame,
  type SeatedPlayer,
  type Tournament,
} from "./api";
import { describe, formatTime, next, useCountdown } from "./blindClock";
import { startFormat } from "./dates";
import { SERVER_UNREACHABLE, smallButton } from "./forms";
import { usePayment } from "./PaymentDialog";
import { paidFor } from "./payments";
import { entries, pointsText } from "./points";
import { SignUp } from "./RegistrationsPage";
import { STATUS_NAMES } from "./tournamentStatus";
import { useTournamentChanges } from "./useTournamentChanges";

type Loaded = { game: GameState; receivedAt: number };

/** Running one tournament: start, the blind clock, the tables, knock-outs and the final table. */
export default function GamePage({
  club,
  tournament,
  onBack,
  onResults,
  onCashier,
  onLog,
}: {
  club: Club;
  tournament: Tournament;
  onBack: () => void;
  /** Opens the finished tournament's results, where places are corrected. */
  onResults: () => void;
  /** Opens the tournament's cashier, where the payments taken here are seen and put right. */
  onCashier: () => void;
  /** Opens the tournament's action log: who did what here, and when. */
  onLog: () => void;
}) {
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [error, setError] = useState("");
  const latestLoad = useRef(0);
  // One action at a time: a second click while the first is on its way is ignored.
  const acting = useRef(false);
  const { askToPay, paymentDialog } = usePayment();

  const show = useCallback((game: GameState) => {
    // Any answer replaces an older one still on its way.
    latestLoad.current++;
    setLoaded({ game, receivedAt: Date.now() });
  }, []);

  const load = useCallback(() => {
    const thisLoad = ++latestLoad.current;
    fetchGame(club.id, tournament.id)
      .then((game) => {
        if (thisLoad !== latestLoad.current) return;
        setLoaded({ game, receivedAt: Date.now() });
        // The clock asks again after a failure at a level's end; a later answer clears it.
        setLoadFailed(false);
      })
      .catch(() => thisLoad === latestLoad.current && setLoadFailed(true));
  }, [club.id, tournament.id]);

  useEffect(load, [load]);
  // A latecomer who signs up in the Telegram bot shows up at once among those waiting.
  useTournamentChanges(club.id, tournament.id, load);

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
  /** A re-entry and an add-on are paid for, and so is a late seat: the buy-in, unless paid on
   * coming. */
  const payFor = (player: Player, action: "reentry" | "addon" | "seat", amount: number) =>
    askToPay(paidFor(action === "seat" ? "buy_in" : action, player), amount, (method) =>
      change(() => actOnPlayer(club.id, tournament.id, player.id, action, method)),
    );
  const seat = (registration: Registration) =>
    payFor(
      registration.player,
      "seat",
      registration.status === "checked_in" ? 0 : tournament.buy_in,
    );
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
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onCashier}
              className="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-700"
            >
              Касса
            </button>
            <button
              type="button"
              onClick={onLog}
              className="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-700"
            >
              Журнал
            </button>
            <button
              type="button"
              onClick={onBack}
              className="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-700"
            >
              Назад к списку
            </button>
          </div>
        </div>
        <BoardLink token={tournament.board_token} />
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
      {game && live && (
        <Tables
          game={game}
          onKnockOut={(playerId) => act(playerId, "knock-out")}
          onAddon={(player) => payFor(player, "addon", tournament.addon_price ?? 0)}
        />
      )}
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
          register={(player) =>
            askToPay(paidFor("buy_in", player), tournament.buy_in, (method) =>
              change(async () => {
                await registerPlayer(club.id, tournament.id, player.id);
                return actOnPlayer(club.id, tournament.id, player.id, "seat", method);
              }),
            )
          }
        >
          <Waiting game={game} onSeat={seat} />
        </SignUp>
      )}
      {game?.status === "finished" && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-white p-4 shadow-sm">
          <p className="font-medium text-slate-900">Турнир завершён</p>
          <button type="button" onClick={onResults} className={smallButton}>
            Результаты и исправление мест
          </button>
        </div>
      )}
      {game && game.out.length > 0 && (
        <Finished
          game={game}
          onReenter={(player) => payFor(player, "reentry", tournament.buy_in)}
          onUndo={(playerId) => act(playerId, "undo-knock-out")}
        />
      )}
      {paymentDialog}
    </div>
  );
}

/** The hall board opens by this link on the club's TV, without login. */
function BoardLink({ token }: { token: string }) {
  const path = `/board/${token}`;
  return (
    <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-600">
      <span>Табло для зала:</span>
      <code className="select-all rounded bg-slate-100 px-2 py-0.5 text-slate-800">
        {window.location.origin}
        {path}
      </code>
      <a href={path} target="_blank" rel="noreferrer" className={smallButton}>
        Открыть табло
      </a>
    </p>
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
  const secondsLeft = useCountdown(structure, clock, receivedAt, onLevelOver);
  const headingId = useId();

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

function Tables({
  game,
  onKnockOut,
  onAddon,
}: {
  game: GameState;
  onKnockOut: (playerId: number) => void;
  onAddon: (player: Player) => void;
}) {
  const tables = [...new Set(game.in_game.map((s) => s.table))].sort((a, b) => a - b);
  // One table left of a tournament that needed more: the final table.
  const final = tables.length === 1 && game.in_game.length + game.out.length > game.seats_per_table;

  function knockOut(seated: SeatedPlayer) {
    if (window.confirm(`Игрок ${seated.player.name} выбыл?`)) onKnockOut(seated.player.id);
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
          onAddon={(s) => onAddon(s.player)}
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

function Waiting({
  game,
  onSeat,
}: {
  game: GameState;
  onSeat: (registration: Registration) => void;
}) {
  if (game.waiting.length === 0) return null;
  return (
    <ul
      aria-label="Ждут посадки"
      className="mb-4 divide-y divide-slate-200 rounded-xl border border-slate-200"
    >
      {game.waiting.map((registration) => (
        <li
          key={registration.player.id}
          aria-label={registration.player.name}
          className="flex items-center gap-3 p-2"
        >
          <p className="flex-1 font-medium text-slate-900">{registration.player.name}</p>
          <button type="button" onClick={() => onSeat(registration)} className={smallButton}>
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
  onUndo,
}: {
  game: GameState;
  onReenter: (player: Player) => void;
  /** Takes back a knock-out marked by mistake; not a re-entry. */
  onUndo: (playerId: number) => void;
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
            {player.points !== null && (
              <span className="font-medium tabular-nums text-slate-900">
                {pointsText(player.points)}
              </span>
            )}
            {!finished && (
              <div className="flex flex-wrap gap-2">
                {game.windows.reentry && (
                  <button
                    type="button"
                    onClick={() => onReenter(player.player)}
                    className={smallButton}
                  >
                    Re-entry
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => onUndo(player.player.id)}
                  className={smallButton}
                >
                  Отменить выбывание
                </button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
