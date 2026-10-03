import { type FormEvent, useEffect, useId, useState } from "react";
import { LogEntry } from "./ActionLogPage";
import {
  type ActionLogEntry,
  type Admin,
  addToTeam,
  type Club,
  fetchClubLog,
  fetchTeam,
  RejectedError,
  removeFromTeam,
  type TeamMemberAdded,
} from "./api";
import { inputClass, labelClass, SERVER_UNREACHABLE, smallButton } from "./forms";
import { formatPhone } from "./phones";

type Loaded =
  | { status: "loading" }
  | { status: "loaded"; team: Admin[]; log: ActionLogEntry[] }
  | { status: "failed" };

const NOBODY = { name: "", phone: "" };

/** Why the server refused, or that it could not be reached. */
function reasons(error: unknown): string[] {
  return error instanceof RejectedError ? error.messages : [SERVER_UNREACHABLE];
}

/** What happened, in words for the owner. */
function addedMessage({ admin, outcome }: TeamMemberAdded): string {
  return outcome === "added" ? `${admin.name} теперь в команде` : `${admin.name} снова в команде`;
}

/** The club's team as its owner sees it: who has access to the admin panel. The owner adds and
 * removes admins; owners are the league's to change. Below, the club's log tells who changed the
 * team and when. Only the owner has this section. */
export default function TeamPage({ club }: { club: Club }) {
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  // Bumped after every change, to read the team and the log afresh.
  const [version, setVersion] = useState(0);
  const [fields, setFields] = useState(NOBODY);
  // Why the admin typed in was not added, or why the one picked was not removed.
  const [errors, setErrors] = useState<string[]>([]);
  const [removalErrors, setRemovalErrors] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const headingId = useId();
  const formHeadingId = useId();
  const logHeadingId = useId();

  useEffect(() => {
    let stale = false;
    Promise.all([fetchTeam(club.id), fetchClubLog(club.id)])
      .then(([team, log]) => !stale && setLoaded({ status: "loaded", team, log }))
      .catch(() => !stale && setLoaded({ status: "failed" }));
    return () => {
      stale = true;
    };
  }, [club.id, version]);

  async function add(event: FormEvent) {
    event.preventDefault();
    setErrors([]);
    setRemovalErrors([]);
    setMessage("");
    setSaving(true);
    try {
      setMessage(addedMessage(await addToTeam(club.id, fields)));
      setFields(NOBODY);
      setVersion((v) => v + 1);
    } catch (error) {
      setErrors(reasons(error));
    } finally {
      setSaving(false);
    }
  }

  async function remove(member: Admin) {
    const question =
      `Убрать из команды: ${member.name}? Вход в админ-панель закроется сразу, имя останется ` +
      "в кассе и журнале.";
    if (!window.confirm(question)) return;
    setErrors([]);
    setRemovalErrors([]);
    setMessage("");
    try {
      await removeFromTeam(club.id, member.id);
      setMessage(`${member.name} больше не в команде`);
    } catch (error) {
      setRemovalErrors(reasons(error));
    }
    setVersion((v) => v + 1);
  }

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby={formHeadingId} className="rounded-2xl bg-white p-6 shadow-sm">
        <h2 id={formHeadingId} className="mb-4 text-lg font-semibold text-slate-900">
          Добавить сотрудника
        </h2>
        <form onSubmit={add} className="flex flex-col gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className={labelClass}>
              Имя
              <input
                required
                value={fields.name}
                onChange={(event) => setFields({ ...fields, name: event.target.value })}
                className={inputClass}
              />
            </label>
            <label className={labelClass}>
              Телефон
              <input
                type="tel"
                required
                placeholder="+7 913 555-12-34"
                value={fields.phone}
                onChange={(event) => setFields({ ...fields, phone: event.target.value })}
                className={inputClass}
              />
            </label>
          </div>
          <p className="text-sm text-slate-600">
            Администратор входит в админ-панель по этому телефону. Владельцев назначает лига.
          </p>
          {errors.length > 0 && (
            <div role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">
              <p className="mb-1 font-medium">Сотрудник не добавлен:</p>
              <ul className="list-disc pl-5">
                {errors.map((error) => (
                  <li key={error}>{error}</li>
                ))}
              </ul>
            </div>
          )}
          <div>
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg px-4 py-2 font-medium text-white disabled:opacity-60"
              style={{ backgroundColor: club.primary_color }}
            >
              Добавить сотрудника
            </button>
          </div>
        </form>
        {message && (
          <p role="status" className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
            {message}
          </p>
        )}
      </section>

      <section aria-labelledby={headingId} className="rounded-2xl bg-white p-6 shadow-sm">
        <h2 id={headingId} className="mb-4 text-lg font-semibold text-slate-900">
          Команда клуба
        </h2>
        {removalErrors.length > 0 && (
          <p role="alert" className="mb-4 rounded-lg bg-red-50 p-4 text-sm text-red-800">
            Сотрудник не убран: {removalErrors.join(" ")}
          </p>
        )}
        {loaded.status === "loading" && <p className="text-slate-600">Загружаем команду…</p>}
        {loaded.status === "failed" && (
          <p role="alert" className="text-red-700">
            Не удалось загрузить команду. Обновите страницу.
          </p>
        )}
        {loaded.status === "loaded" && (
          <ul
            aria-label="Команда клуба"
            className="divide-y divide-slate-200 rounded-xl border border-slate-200"
          >
            {loaded.team.map((member) => (
              <li
                key={member.id}
                aria-label={member.name}
                className="flex flex-wrap items-center gap-x-4 gap-y-1 p-3"
              >
                <span className="min-w-48 flex-1 font-medium text-slate-900">{member.name}</span>
                <span className="text-slate-600">{formatPhone(member.phone)}</span>
                {member.role === "owner" ? (
                  <span className="w-20 text-right text-sm text-slate-500">Владелец</span>
                ) : (
                  <button
                    type="button"
                    onClick={() => remove(member)}
                    className={`${smallButton} w-20`}
                  >
                    Убрать
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      {loaded.status === "loaded" && (
        <section aria-labelledby={logHeadingId} className="rounded-2xl bg-white p-6 shadow-sm">
          <h2 id={logHeadingId} className="mb-4 text-lg font-semibold text-slate-900">
            Журнал клуба
          </h2>
          {loaded.log.length === 0 ? (
            <p className="text-sm text-slate-500">Записей пока нет</p>
          ) : (
            <ul
              aria-label="Журнал клуба"
              className="divide-y divide-slate-200 rounded-xl border border-slate-200"
            >
              {loaded.log.map((entry) => (
                <LogEntry key={entry.id} entry={entry} />
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
