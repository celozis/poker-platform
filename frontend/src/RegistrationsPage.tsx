import { type ReactNode, useCallback, useEffect, useId, useRef, useState } from "react";
import {
  addPlayer,
  cancelRegistration,
  type Club,
  fetchRegistrations,
  type Player,
  type Registration,
  registerPlayer,
  RejectedError,
  setCheckedIn,
  type Tournament,
  type TournamentRegistrations,
} from "./api";
import { startFormat } from "./dates";
import { inputClass, SERVER_UNREACHABLE, smallButton } from "./forms";
import { formatPhone } from "./phones";
import PlayerForm, { addedMessage } from "./PlayerForm";
import { usePlayerSearch } from "./usePlayerSearch";

const REGISTRATION_STATUS_NAMES: Record<Registration["status"], string> = {
  registered: "Зарегистрирован",
  checked_in: "Пришёл",
  in_game: "В игре",
  out: "Игра окончена",
};

type LoadState =
  | { status: "loading" }
  | { status: "loaded"; data: TournamentRegistrations }
  | { status: "failed" };

/** One tournament's registered players: sign-ups before the start, check-ins on the day. */
export default function RegistrationsPage({
  club,
  tournament,
  onBack,
}: {
  club: Club;
  tournament: Tournament;
  onBack: () => void;
}) {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [actionError, setActionError] = useState("");
  const latestLoad = useRef(0);

  const load = useCallback(() => {
    // Quick clicks reload several times; only the latest answer may replace the list.
    const thisLoad = ++latestLoad.current;
    fetchRegistrations(club.id, tournament.id)
      .then((data) => thisLoad === latestLoad.current && setState({ status: "loaded", data }))
      .catch(() => thisLoad === latestLoad.current && setState({ status: "failed" }));
  }, [club.id, tournament.id]);

  useEffect(load, [load]);

  /** Runs a change and reloads the list; a refusal is shown above the list. */
  async function change(action: () => Promise<unknown>) {
    setActionError("");
    try {
      await action();
    } catch (error) {
      setActionError(error instanceof RejectedError ? error.messages.join("\n") : SERVER_UNREACHABLE);
    }
    load();
  }

  function cancel(registration: Registration) {
    const { player } = registration;
    if (!window.confirm(`Снять ${player.name} с регистрации на турнир?`)) return;
    change(() => cancelRegistration(club.id, tournament.id, player.id));
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-2xl bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">{tournament.name}</h2>
            <p className="text-sm text-slate-600">
              {startFormat.format(new Date(tournament.starts_at))}
              {tournament.status === "cancelled" && " · отменён"}
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

      {state.status === "loading" && <p className="text-slate-600">Загружаем регистрации…</p>}
      {state.status === "failed" && (
        <p role="alert" className="text-red-700">
          Не удалось загрузить регистрации. Обновите страницу.
        </p>
      )}
      {state.status === "loaded" && (
        <>
          {state.data.registration_open ? (
            <SignUp
              club={club}
              registeredIds={new Set(state.data.registrations.map((r) => r.player.id))}
              register={(playerId) => change(() => registerPlayer(club.id, tournament.id, playerId))}
            />
          ) : (
            <p className="rounded-2xl bg-white p-4 text-sm text-slate-600 shadow-sm">
              Регистрация закрыта: турнир уже начался или отменён.
            </p>
          )}
          <RegisteredList
            data={state.data}
            error={actionError}
            onCheckIn={(registration, arrived) =>
              change(() => setCheckedIn(club.id, tournament.id, registration.player.id, arrived))
            }
            onCancel={cancel}
          />
        </>
      )}
    </div>
  );
}

function RegisteredList({
  data,
  error,
  onCheckIn,
  onCancel,
}: {
  data: TournamentRegistrations;
  error: string;
  onCheckIn: (registration: Registration, arrived: boolean) => void;
  onCancel: (registration: Registration) => void;
}) {
  const { registrations, drop_out_open, check_in_open } = data;
  // Everyone seated or out has come too.
  const arrived = registrations.filter((r) => r.status !== "registered").length;
  return (
    <section aria-labelledby="registered" className="rounded-2xl bg-white p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h3 id="registered" className="text-lg font-semibold text-slate-900">
          Зарегистрированные
        </h3>
        <p className="text-sm text-slate-600">
          Зарегистрировано: {registrations.length}, пришли: {arrived}
        </p>
      </div>
      {!check_in_open && (
        <p className="mb-4 text-xs text-slate-500">
          Отметить приход можно с 12 часов до начала турнира до 12 часов после начала.
        </p>
      )}
      {error && (
        <p role="alert" className="mb-4 whitespace-pre-line rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}
      {registrations.length === 0 ? (
        <p className="text-sm text-slate-500">Пока никто не зарегистрирован</p>
      ) : (
        <ul
          aria-label="Зарегистрированные игроки"
          className="divide-y divide-slate-200 rounded-xl border border-slate-200"
        >
          {registrations.map((registration) => {
            const { player, status } = registration;
            const checkedIn = status !== "registered";
            return (
              <li
                key={player.id}
                aria-label={player.name}
                className="flex flex-wrap items-center gap-x-4 gap-y-2 p-3"
              >
                <div className="min-w-48 flex-1">
                  <p className="font-medium text-slate-900">{player.name}</p>
                  <p className="text-sm text-slate-600">{formatPhone(player.phone)}</p>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-sm ${
                    checkedIn ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {REGISTRATION_STATUS_NAMES[status]}
                </span>
                {(check_in_open || drop_out_open) && (
                  <div className="flex flex-wrap gap-2">
                    {check_in_open && (
                      <button
                        type="button"
                        onClick={() => onCheckIn(registration, !checkedIn)}
                        className={smallButton}
                      >
                        {checkedIn ? "Отменить приход" : "Отметить приход"}
                      </button>
                    )}
                    {drop_out_open && (
                      <button
                        type="button"
                        onClick={() => onCancel(registration)}
                        className="rounded-lg border border-red-200 px-3 py-1 text-sm text-red-700"
                      >
                        Снять с регистрации
                      </button>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** Finding a club player to register, or adding a new one and registering them at once.
 * Late registration reuses it with its own title and button labels. */
export function SignUp({
  club,
  registeredIds,
  register,
  title = "Записать игрока",
  registerLabel = "Зарегистрировать",
  addLabel = "Добавить и зарегистрировать",
  children,
}: {
  club: Club;
  /** Players already in the tournament, who are not offered again. */
  registeredIds: Set<number>;
  /** Registers the player; the caller shows a refusal. */
  register: (playerId: number) => void;
  title?: string;
  registerLabel?: string;
  addLabel?: string;
  /** Shown under the title, before the search. */
  children?: ReactNode;
}) {
  const [query, setQuery] = useState("");
  const [addingNew, setAddingNew] = useState(false);
  const [notice, setNotice] = useState("");
  const { state } = usePlayerSearch(club.id, query);
  const headingId = useId();

  return (
    <section aria-labelledby={headingId} className="rounded-2xl bg-white p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h3 id={headingId} className="text-lg font-semibold text-slate-900">
          {title}
        </h3>
        <button type="button" onClick={() => setAddingNew(!addingNew)} className={smallButton}>
          {addingNew ? "Скрыть форму" : "Новый игрок"}
        </button>
      </div>
      {addingNew && (
        <div className="mb-6 rounded-xl border border-slate-200 p-4">
          <PlayerForm
            primaryColor={club.primary_color}
            submitLabel={addLabel}
            add={async (input) => {
              setNotice("");
              const added = await addPlayer(club.id, input);
              // The player is on the club's list now, whatever happens to the registration.
              setAddingNew(false);
              setNotice(addedMessage(added));
              register(added.player.id);
            }}
          />
        </div>
      )}
      {children}
      {notice && (
        <p role="status" className="mb-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
          {notice}
        </p>
      )}
      <input
        type="search"
        aria-label="Найти игрока клуба"
        placeholder="Имя или телефон игрока клуба"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        className={`${inputClass} w-full`}
      />
      {query.trim() !== "" && state.status === "loaded" && (
        <FoundPlayers
          players={state.players}
          registeredIds={registeredIds}
          register={register}
          registerLabel={registerLabel}
        />
      )}
      {query.trim() !== "" && state.status === "failed" && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          Не удалось найти игроков. Попробуйте ещё раз.
        </p>
      )}
    </section>
  );
}

function FoundPlayers({
  players,
  registeredIds,
  register,
  registerLabel,
}: {
  players: Player[];
  registeredIds: Set<number>;
  register: (playerId: number) => void;
  registerLabel: string;
}) {
  if (players.length === 0) {
    return (
      <p className="mt-3 text-sm text-slate-500">
        Никого не нашли. Новичка добавьте кнопкой «Новый игрок».
      </p>
    );
  }
  return (
    <ul
      aria-label="Найденные игроки"
      className="mt-3 divide-y divide-slate-200 rounded-xl border border-slate-200"
    >
      {players.map((player) => (
        <li
          key={player.id}
          aria-label={player.name}
          className="flex flex-wrap items-center gap-x-4 gap-y-2 p-3"
        >
          <div className="min-w-48 flex-1">
            <p className="font-medium text-slate-900">{player.name}</p>
            <p className="text-sm text-slate-600">{formatPhone(player.phone)}</p>
          </div>
          {registeredIds.has(player.id) ? (
            <span className="text-sm text-slate-500">Уже зарегистрирован</span>
          ) : (
            <button type="button" onClick={() => register(player.id)} className={smallButton}>
              {registerLabel}
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}
