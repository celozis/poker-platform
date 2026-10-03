import { useEffect, useId, useState } from "react";
import { type Club, fetchActionLog, type LoggedAction, type ActionLogEntry, type Player, type Tournament } from "./api";
import { startFormat } from "./dates";
import { inputClass, labelClass } from "./forms";

const ACTION_NAMES: Record<LoggedAction, string> = {
  registered: "Запись на турнир",
  registration_cancelled: "Отмена записи",
  checked_in: "Приход",
  check_in_undone: "Отмена прихода",
  started: "Старт турнира",
  paused: "Пауза",
  resumed: "Продолжение",
  level_changed: "Смена уровня",
  knocked_out: "Выбывание",
  knock_out_undone: "Отмена выбывания",
  reentry: "Re-entry",
  addon: "Add-on",
  seated_late: "Посадка по поздней регистрации",
  moved: "Пересадка",
  final_table: "Финальный стол",
  place_corrected: "Исправление места",
  storno: "Сторно",
  payment_method_changed: "Смена способа оплаты",
  tournament_edited: "Изменение турнира",
  tournament_cancelled: "Отмена турнира",
};

/** Who did it, as the log shows it: the admin, or the player themselves in the bot. */
const PLAYER_HIMSELF = "игрок";

const timeFormat = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

type Loaded = { status: "loading" } | { status: "loaded"; log: ActionLogEntry[] } | { status: "failed" };

/** A tournament's action log: who did what, when and to which player, the latest first, so that
 * the club can settle a dispute. Filtered by player, it is one player's evening. */
export default function ActionLogPage({
  club,
  tournament,
  onBack,
}: {
  club: Club;
  tournament: Tournament;
  onBack: () => void;
}) {
  const [playerId, setPlayerId] = useState<number | undefined>(undefined);
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  // Everyone in the whole log, to choose from; a filtered log has only the one player.
  const [players, setPlayers] = useState<Player[]>([]);
  const filterId = useId();

  useEffect(() => {
    let stale = false;
    setLoaded({ status: "loading" });
    fetchActionLog(club.id, tournament.id, playerId)
      .then((log) => {
        if (stale) return;
        setLoaded({ status: "loaded", log });
        if (playerId === undefined) setPlayers(playersIn(log));
      })
      .catch(() => !stale && setLoaded({ status: "failed" }));
    return () => {
      stale = true;
    };
  }, [club.id, tournament.id, playerId]);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-2xl bg-white p-6 shadow-sm">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{tournament.name}</h2>
          <p className="text-sm text-slate-600">
            {startFormat.format(new Date(tournament.starts_at))} · журнал действий
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

      <section className="rounded-2xl bg-white p-6 shadow-sm">
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <label htmlFor={filterId} className={labelClass}>
            Игрок
            <select
              id={filterId}
              value={playerId ?? ""}
              onChange={(event) =>
                setPlayerId(event.target.value === "" ? undefined : Number(event.target.value))
              }
              className={inputClass}
            >
              <option value="">Все игроки</option>
              {players.map((player) => (
                <option key={player.id} value={player.id}>
                  {player.name}
                </option>
              ))}
            </select>
          </label>
          {loaded.status === "loaded" && (
            <p className="text-sm text-slate-500">Записей: {loaded.log.length}</p>
          )}
        </div>
        {loaded.status === "loading" && <p className="text-slate-600">Загружаем журнал…</p>}
        {loaded.status === "failed" && (
          <p role="alert" className="text-red-700">
            Не удалось загрузить журнал. Обновите страницу.
          </p>
        )}
        {loaded.status === "loaded" &&
          (loaded.log.length === 0 ? (
            <p className="text-sm text-slate-500">Записей пока нет</p>
          ) : (
            <ul
              aria-label="Журнал действий"
              className="divide-y divide-slate-200 rounded-xl border border-slate-200"
            >
              {loaded.log.map((entry) => (
                <Entry key={entry.id} entry={entry} />
              ))}
            </ul>
          ))}
      </section>
    </div>
  );
}

/** The players the log mentions, by name. */
function playersIn(log: ActionLogEntry[]): Player[] {
  const byId = new Map(log.flatMap((entry) => (entry.player ? [[entry.player.id, entry.player]] : [])));
  return [...byId.values()].sort((a, b) => a.name.localeCompare(b.name, "ru"));
}

function Entry({ entry }: { entry: ActionLogEntry }) {
  const who = entry.admin?.name ?? PLAYER_HIMSELF;
  return (
    <li className="flex flex-wrap gap-x-4 gap-y-1 p-3">
      <p className="w-32 text-sm text-slate-500">{timeFormat.format(new Date(entry.created_at))}</p>
      <div className="min-w-48 flex-1">
        <p className="font-medium text-slate-900">
          {ACTION_NAMES[entry.action]}
          {entry.player && ` · ${entry.player.name}`}
        </p>
        <p className="text-sm text-slate-600">
          {who}
          {entry.details && ` · ${entry.details}`}
        </p>
      </div>
    </li>
  );
}
