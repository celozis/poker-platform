import { useCallback, useEffect, useState } from "react";
import {
  cancelTournament,
  type Club,
  createTournament,
  fetchTournaments,
  type Tournament,
  type TournamentList,
  RejectedError,
  updateTournament,
} from "./api";
import TournamentForm from "./TournamentForm";

const startFormat = new Intl.DateTimeFormat("ru-RU", {
  weekday: "short",
  day: "numeric",
  month: "long",
  hour: "2-digit",
  minute: "2-digit",
});
const numberFormat = new Intl.NumberFormat("ru-RU");

type ListState =
  | { status: "loading" }
  | { status: "loaded"; tournaments: TournamentList }
  | { status: "failed" };

type View = { screen: "list" } | { screen: "create" } | { screen: "edit"; tournament: Tournament };

/** The club's tournaments: upcoming ones can be edited or cancelled, past ones only viewed. */
export default function TournamentsPage({ club }: { club: Club }) {
  const [list, setList] = useState<ListState>({ status: "loading" });
  const [view, setView] = useState<View>({ screen: "list" });

  const loadList = useCallback(() => {
    fetchTournaments(club.id)
      .then((tournaments) => setList({ status: "loaded", tournaments }))
      .catch(() => setList({ status: "failed" }));
  }, [club.id]);

  useEffect(loadList, [loadList]);

  function backToList() {
    setView({ screen: "list" });
    loadList();
  }

  function cancel(tournament: Tournament) {
    const question = `Отменить турнир «${tournament.name}»? Вернуть его будет нельзя.`;
    if (!window.confirm(question)) return;
    cancelTournament(club.id, tournament.id)
      .then(loadList)
      .catch((error) =>
        window.alert(
          error instanceof RejectedError
            ? error.messages.join("\n")
            : "Не удалось отменить турнир: нет связи с сервером. Попробуйте ещё раз.",
        ),
      );
  }

  if (view.screen !== "list") {
    const editing = view.screen === "edit" ? view.tournament : undefined;
    return (
      <div className="rounded-2xl bg-white p-6 shadow-sm">
        <TournamentForm
          tournament={editing}
          primaryColor={club.primary_color}
          save={async (input) => {
            await (editing
              ? updateTournament(club.id, editing.id, input)
              : createTournament(club.id, input));
            backToList();
          }}
          onClose={backToList}
        />
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-white p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-900">Турниры</h2>
        <button
          type="button"
          onClick={() => setView({ screen: "create" })}
          className="rounded-lg px-4 py-2 font-medium text-white"
          style={{ backgroundColor: club.primary_color }}
        >
          Создать турнир
        </button>
      </div>
      {list.status === "loading" && <p className="text-slate-600">Загружаем турниры…</p>}
      {list.status === "failed" && (
        <p role="alert" className="text-red-700">
          Не удалось загрузить турниры. Обновите страницу.
        </p>
      )}
      {list.status === "loaded" && (
        <div className="flex flex-col gap-6">
          <TournamentSection
            title="Предстоящие"
            empty="Предстоящих турниров нет"
            tournaments={list.tournaments.upcoming}
            onEdit={(tournament) => setView({ screen: "edit", tournament })}
            onCancel={cancel}
          />
          <TournamentSection
            title="Прошедшие"
            empty="Прошедших турниров пока нет"
            tournaments={list.tournaments.past}
          />
        </div>
      )}
    </div>
  );
}

function TournamentSection({
  title,
  empty,
  tournaments,
  onEdit,
  onCancel,
}: {
  title: string;
  empty: string;
  tournaments: Tournament[];
  /** Given only for tournaments that have not started yet. */
  onEdit?: (tournament: Tournament) => void;
  onCancel?: (tournament: Tournament) => void;
}) {
  const headingId = `tournaments-${title}`;
  return (
    <section aria-labelledby={headingId}>
      <h3 id={headingId} className="mb-2 font-medium text-slate-700">
        {title}
      </h3>
      {tournaments.length === 0 ? (
        <p className="text-sm text-slate-500">{empty}</p>
      ) : (
        <ul className="divide-y divide-slate-200 rounded-xl border border-slate-200">
          {tournaments.map((tournament) => {
            const manageable = tournament.status === "scheduled";
            return (
              <TournamentRow
                key={tournament.id}
                tournament={tournament}
                onEdit={onEdit && manageable ? () => onEdit(tournament) : undefined}
                onCancel={onCancel && manageable ? () => onCancel(tournament) : undefined}
              />
            );
          })}
        </ul>
      )}
    </section>
  );
}

function TournamentRow({
  tournament,
  onEdit,
  onCancel,
}: {
  tournament: Tournament;
  onEdit?: () => void;
  onCancel?: () => void;
}) {
  const cancelled = tournament.status === "cancelled";
  return (
    <li aria-label={tournament.name} className="flex flex-wrap items-center gap-x-4 gap-y-2 p-3">
      {/* On a phone the buttons wrap below the details instead of squeezing them. */}
      <div className="min-w-48 flex-1">
        <p className={`font-medium ${cancelled ? "text-slate-400 line-through" : "text-slate-900"}`}>
          {tournament.name}
        </p>
        <p className="text-sm text-slate-600">
          {startFormat.format(new Date(tournament.starts_at))} · бай-ин{" "}
          {numberFormat.format(tournament.buy_in)} ₽ · стек{" "}
          {numberFormat.format(tournament.starting_stack)}
        </p>
      </div>
      {cancelled && (
        <span className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-600">Отменён</span>
      )}
      {(onEdit || onCancel) && (
        <div className="flex gap-2">
          {onEdit && (
            <button
              type="button"
              onClick={onEdit}
              className="rounded-lg border border-slate-300 px-3 py-1 text-sm"
            >
              Изменить
            </button>
          )}
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="rounded-lg border border-red-200 px-3 py-1 text-sm text-red-700"
            >
              Отменить турнир
            </button>
          )}
        </div>
      )}
    </li>
  );
}
