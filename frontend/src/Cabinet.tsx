import { type ReactNode, useEffect, useId, useState } from "react";
import { type CabinetClub, fetchCabinet, logout, type PlayerCabinet } from "./api";
import { dayFormat, startFormat } from "./dates";
import LeagueBrand from "./LeagueBrand";
import LoginPage from "./LoginPage";
import { money } from "./payments";
import { formatPhone } from "./phones";
import { entries, pointsText, tournamentsText } from "./points";

type SessionState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "loggedIn"; cabinet: PlayerCabinet };

/** The player's web cabinet: they log in by phone and code and see their own data. Most players
 * open it on a phone, so it is laid out for a narrow screen first. */
export default function Cabinet() {
  const [session, setSession] = useState<SessionState>({ status: "loading" });

  function loadSession() {
    fetchCabinet()
      .then((cabinet) =>
        setSession(cabinet ? { status: "loggedIn", cabinet } : { status: "anonymous" }),
      )
      .catch(() => setSession({ status: "anonymous" }));
  }

  useEffect(loadSession, []);

  function handleLogout() {
    // Only leave the cabinet once the server has dropped the session; otherwise it is still live.
    logout("cabinet")
      .then(() => setSession({ status: "anonymous" }))
      .catch(() => window.alert("Не удалось выйти: нет связи с сервером. Попробуйте ещё раз."));
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-100">
      {session.status === "anonymous" && (
        <LoginPage to="cabinet" title="Личный кабинет игрока" onLoggedIn={loadSession} />
      )}
      {session.status === "loggedIn" && (
        <CabinetPage cabinet={session.cabinet} onLogout={handleLogout} />
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="rounded-2xl bg-white p-4 shadow-sm sm:p-6">
      <h2 id={headingId} className="mb-3 text-lg font-semibold text-slate-900">
        {title}
      </h2>
      {children}
    </section>
  );
}

function CabinetPage({ cabinet, onLogout }: { cabinet: PlayerCabinet; onLogout: () => void }) {
  const { player, season, clubs, history } = cabinet;
  return (
    <>
      <header className="bg-slate-900 text-white shadow">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-3">
          <LeagueBrand className="min-w-0 flex-1" />
          <button
            type="button"
            onClick={onLogout}
            className="shrink-0 rounded-lg bg-white px-3 py-1.5 text-sm font-medium text-slate-900"
          >
            Выйти
          </button>
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-4 py-6">
        <Section title="Профиль">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <dt className="text-slate-500">Имя</dt>
            <dd className="font-medium text-slate-900">{player.name}</dd>
            <dt className="text-slate-500">Телефон</dt>
            <dd className="text-slate-900">{formatPhone(player.phone)}</dd>
            <dt className="text-slate-500">{clubs.length > 1 ? "Клубы" : "Клуб"}</dt>
            <dd className="text-slate-900">
              {clubs.length > 0
                ? clubs.map((c) => c.club.name).join(", ")
                : "пока нет: выберите клуб в Telegram-боте лиги"}
            </dd>
            <dt className="text-slate-500">Telegram</dt>
            <dd className="text-slate-900">{player.telegram_linked ? "привязан" : "не привязан"}</dd>
          </dl>
        </Section>
        <Section title="Рейтинг">
          <p className="mb-3 text-sm text-slate-600">{season.name}</p>
          {clubs.length === 0 && <NoClub />}
          <ul className="flex flex-col gap-2">
            {clubs.map(({ club, rating }) => (
              <li
                key={club.id}
                className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 rounded-xl border border-slate-200 px-3 py-2"
              >
                <span className="font-medium text-slate-900">{club.name}</span>
                {rating ? (
                  <span className="text-sm text-slate-700">
                    <span className="font-semibold text-slate-900">{rating.position}-е место</span>
                    {" · "}
                    {pointsText(rating.points)} · {tournamentsText(rating.tournaments)}
                  </span>
                ) : (
                  <span className="text-sm text-slate-500">
                    Пока нет в рейтинге: сыграйте турнир клуба в этом сезоне
                  </span>
                )}
              </li>
            ))}
          </ul>
        </Section>
        <Section title="Ближайшие турниры">
          {clubs.length === 0 && <NoClub />}
          <div className="flex flex-col gap-4">
            {clubs.map((cabinetClub) => (
              <ClubSchedule key={cabinetClub.club.id} cabinetClub={cabinetClub} />
            ))}
          </div>
        </Section>
        <Section title="История турниров">
          {history.length === 0 ? (
            <p className="text-sm text-slate-500">Вы ещё не сыграли ни одного турнира</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {history.map((played) => (
                <li
                  key={`${played.starts_at} ${played.club} ${played.tournament}`}
                  className="rounded-xl border border-slate-200 px-3 py-2"
                >
                  <p className="text-sm text-slate-500">
                    {dayFormat.format(new Date(played.starts_at))} · {played.club}
                  </p>
                  <p className="font-medium text-slate-900">{played.tournament}</p>
                  <p className="text-sm text-slate-700">
                    <span className="font-semibold text-slate-900">
                      {played.place}-е место из {played.players}
                    </span>
                    {" · "}
                    {pointsText(played.points)}
                    {entries(played) && ` · ${entries(played)}`}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </main>
    </>
  );
}

const badge = "rounded-full px-2 py-0.5 text-xs font-medium";

/** Before the player has chosen a club in the bot or come to one, no club lists them yet. */
function NoClub() {
  return <p className="text-sm text-slate-500">Вы пока не в списке ни одного клуба</p>;
}

function ClubSchedule({ cabinetClub: { club, schedule } }: { cabinetClub: CabinetClub }) {
  const headingId = useId();
  return (
    <div>
      <h3 id={headingId} className="mb-2 font-medium text-slate-900">
        {club.name}
      </h3>
      {schedule.length === 0 ? (
        <p className="text-sm text-slate-500">Запланированных турниров пока нет</p>
      ) : (
        <ul aria-labelledby={headingId} className="flex flex-col gap-2">
          {schedule.map((t) => (
            <li
              key={`${t.starts_at} ${t.name}`}
              className="rounded-xl border border-slate-200 px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-slate-900">{t.name}</span>
                {t.going_on && <span className={`${badge} bg-green-100 text-green-800`}>Идёт</span>}
                {t.registered && (
                  <span className={`${badge} bg-blue-100 text-blue-800`}>Вы записаны</span>
                )}
              </div>
              <p className="text-sm text-slate-600">
                {startFormat.format(new Date(t.starts_at))} · бай-ин {money(t.buy_in)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
