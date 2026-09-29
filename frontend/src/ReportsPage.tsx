import { useEffect, useId, useState } from "react";
import {
  type Club,
  type ClubReport,
  fetchReport,
  RejectedError,
  type RatingRow,
  type ReportPeriod,
  reportCsvUrl,
} from "./api";
import { dayMonth, isoDay } from "./dates";
import { inputClass, labelClass, smallButton } from "./forms";
import { KIND_NAMES, METHOD_NAMES, money } from "./payments";

/** From the first of this month to today. */
function thisMonth(): ReportPeriod {
  const today = new Date();
  return { from: isoDay(new Date(today.getFullYear(), today.getMonth(), 1)), to: isoDay(today) };
}

const average = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

type Loaded =
  | { status: "loading" }
  | { status: "loaded"; report: ClubReport }
  | { status: "rejected"; messages: string[] }
  | { status: "failed" };

const cell = "px-3 py-2";
const numberCell = `${cell} text-right tabular-nums`;
const tableFrame = "overflow-x-auto rounded-xl border border-slate-200";
const headRow = "bg-slate-50 text-left text-sm text-slate-600";

/** The club owner's report of a period: the money, the attendance and the best players of the
 * tournaments that start in it. Only the owner has this section. */
export default function ReportsPage({ club }: { club: Club }) {
  const [period, setPeriod] = useState<ReportPeriod>(thisMonth);
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const headingId = useId();
  // A cleared date input has no day: nothing to ask for until both are filled in.
  const complete = period.from !== "" && period.to !== "";

  useEffect(() => {
    if (!complete) return;
    let stale = false;
    setLoaded({ status: "loading" });
    fetchReport(club.id, period)
      .then((report) => !stale && setLoaded({ status: "loaded", report }))
      .catch(
        (error) =>
          !stale &&
          setLoaded(
            error instanceof RejectedError
              ? { status: "rejected", messages: error.messages }
              : { status: "failed" },
          ),
      );
    return () => {
      stale = true;
    };
  }, [club.id, period, complete]);

  // What was loaded for a period, as long as the period is still whole.
  const shown: Loaded | null = complete ? loaded : null;
  const report = shown?.status === "loaded" ? shown.report : null;

  return (
    <section aria-labelledby={headingId} className="rounded-2xl bg-white p-6 shadow-sm">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <h2 id={headingId} className="w-full text-lg font-semibold text-slate-900">
            Отчёты клуба
          </h2>
          <label className={labelClass}>
            С
            <input
              type="date"
              value={period.from}
              onChange={(event) => setPeriod({ ...period, from: event.target.value })}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            По
            <input
              type="date"
              value={period.to}
              onChange={(event) => setPeriod({ ...period, to: event.target.value })}
              className={inputClass}
            />
          </label>
        </div>
        {report && (
          <a href={reportCsvUrl(club.id, period)} download className={smallButton}>
            Выгрузить в CSV
          </a>
        )}
      </div>
      {!complete && <p className="text-slate-600">Выберите начало и конец периода</p>}
      {shown?.status === "loading" && <p className="text-slate-600">Загружаем отчёт…</p>}
      {shown?.status === "rejected" && (
        <ul role="alert" className="text-red-700">
          {shown.messages.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
      {shown?.status === "failed" && (
        <p role="alert" className="text-red-700">
          Не удалось загрузить отчёт. Обновите страницу.
        </p>
      )}
      {report && (
        <div className="flex flex-col gap-8">
          <FinancesPart report={report} />
          <AttendancePart report={report} />
          <BestPlayersPart report={report} />
        </div>
      )}
    </section>
  );
}

function FinancesPart({ report }: { report: ClubReport }) {
  const { finances } = report;
  const headingId = useId();
  return (
    <section aria-labelledby={headingId}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={headingId} className="font-semibold text-slate-900">
          Финансы
        </h3>
        <p className="text-sm text-slate-600">Турниров проведено: {finances.tournaments}</p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className={tableFrame}>
          <table aria-label="Выручка по операциям" className="w-full text-sm">
            <thead className={headRow}>
              <tr>
                <th scope="col" className={cell}>Операция</th>
                <th scope="col" className={`${cell} text-right`}>Кол-во</th>
                <th scope="col" className={`${cell} text-right`}>Сумма</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {finances.by_kind.map((total) => (
                <tr key={total.kind}>
                  <td className={cell}>{KIND_NAMES[total.kind]}</td>
                  <td className={numberCell}>{total.count}</td>
                  <td className={numberCell}>{money(total.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className={tableFrame}>
          <table aria-label="Выручка по способам оплаты" className="w-full text-sm">
            <thead className={headRow}>
              <tr>
                <th scope="col" className={cell}>Способ оплаты</th>
                <th scope="col" className={`${cell} text-right`}>Сумма</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {finances.by_method.map((total) => (
                <tr key={total.payment_method}>
                  <td className={cell}>{METHOD_NAMES[total.payment_method]}</td>
                  <td className={numberCell}>{money(total.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <p className="mt-3 text-right font-semibold text-slate-900">Всего: {money(finances.total)}</p>
    </section>
  );
}

function AttendancePart({ report }: { report: ClubReport }) {
  const { attendance } = report;
  const headingId = useId();
  return (
    <section aria-labelledby={headingId}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={headingId} className="font-semibold text-slate-900">
          Посещаемость
        </h3>
        <p className="text-sm text-slate-600">
          {attendance.average_players === null
            ? "Турниров не было"
            : `В среднем ${average.format(attendance.average_players)} игрока на турнир`}
        </p>
      </div>
      <div className={tableFrame}>
        <table aria-label="Посещаемость по неделям" className="w-full text-sm">
          <thead className={headRow}>
            <tr>
              <th scope="col" className={cell}>Неделя</th>
              <th scope="col" className={`${cell} text-right`}>Турниров</th>
              <th scope="col" className={`${cell} text-right`}>Участников</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {attendance.weeks.map((week) => (
              <tr key={week.first_day}>
                <td className={cell}>
                  {dayMonth(week.first_day)} – {dayMonth(week.last_day)}
                </td>
                <td className={numberCell}>{week.tournaments}</td>
                <td className={numberCell}>{week.participants}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function BestPlayersPart({ report }: { report: ClubReport }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId}>
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h3 id={headingId} className="font-semibold text-slate-900">
          Лучшие игроки
        </h3>
        <p className="text-sm text-slate-600">По завершённым турнирам, как в рейтинге клуба</p>
      </div>
      {report.top_by_points.length === 0 ? (
        <p className="text-sm text-slate-500">За период нет завершённых турниров</p>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          <BestPlayers name="Лучшие по очкам" rows={report.top_by_points} by="points" />
          <BestPlayers name="Лучшие по числу турниров" rows={report.top_by_tournaments} by="tournaments" />
        </div>
      )}
    </section>
  );
}

const RANKED_BY = {
  points: [
    { name: "Очки", value: (row: RatingRow) => row.points },
    { name: "Турниров", value: (row: RatingRow) => row.tournaments },
  ],
  tournaments: [
    { name: "Турниров", value: (row: RatingRow) => row.tournaments },
    { name: "Очки", value: (row: RatingRow) => row.points },
  ],
};

/** The best players, the column they are ranked by first after the name. */
function BestPlayers({ name, rows, by }: { name: string; rows: RatingRow[]; by: keyof typeof RANKED_BY }) {
  const [first, second] = RANKED_BY[by];
  return (
    <div className={tableFrame}>
      <table aria-label={name} className="w-full text-sm">
        <caption className="bg-slate-50 px-3 pt-2 text-left font-medium text-slate-700">{name}</caption>
        <thead className={headRow}>
          <tr>
            <th scope="col" className={`${cell} w-16`}>Место</th>
            <th scope="col" className={cell}>Игрок</th>
            <th scope="col" className={`${cell} text-right`}>{first.name}</th>
            <th scope="col" className={`${cell} text-right`}>{second.name}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200">
          {rows.map((row) => (
            <tr key={row.player.id}>
              <td className={`${cell} font-medium text-slate-900`}>{row.position}</td>
              <td className={`${cell} text-slate-900`}>{row.player.name}</td>
              <td className={`${numberCell} font-semibold text-slate-900`}>{first.value(row)}</td>
              <td className={`${numberCell} text-slate-600`}>{second.value(row)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
