import { useEffect, useId, useState } from "react";
import { type Club, type ClubRating, fetchRating, type Season } from "./api";
import { smallButton } from "./forms";

// Season days come as "2026-07-01"; read in UTC, so that no time zone moves them a day.
const dayMonth = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", timeZone: "UTC" });

/** "1 июля — 31 декабря 2026": a season is a half of one year. */
function seasonDays(season: Season): string {
  const first = new Date(season.first_day);
  const last = new Date(season.last_day);
  return `${dayMonth.format(first)} — ${dayMonth.format(last)} ${last.getUTCFullYear()}`;
}

type Loaded =
  | { status: "loading" }
  | { status: "loaded"; rating: ClubRating }
  | { status: "failed" };

/** The club rating of the current season, by points; earlier seasons can be looked back at. */
export default function RatingPage({ club }: { club: Club }) {
  // The season shown: undefined for the current one.
  const [season, setSeason] = useState<string | undefined>(undefined);
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const headingId = useId();

  useEffect(() => {
    let stale = false;
    fetchRating(club.id, season)
      .then((rating) => !stale && setLoaded({ status: "loaded", rating }))
      .catch(() => !stale && setLoaded({ status: "failed" }));
    return () => {
      stale = true;
    };
  }, [club.id, season]);

  const rating = loaded.status === "loaded" ? loaded.rating : null;

  return (
    <section aria-labelledby={headingId} className="rounded-2xl bg-white p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id={headingId} className="text-lg font-semibold text-slate-900">
            Рейтинг клуба
          </h2>
          {rating && (
            <p className="text-sm text-slate-600">
              <span className="font-medium text-slate-900">{rating.season.name}</span>
              {" · "}
              <span>{seasonDays(rating.season)}</span>
            </p>
          )}
        </div>
        {rating && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setSeason(rating.previous_season)}
              className={smallButton}
            >
              Предыдущий сезон
            </button>
            {rating.next_season && (
              <button
                type="button"
                onClick={() => setSeason(rating.next_season ?? undefined)}
                className={smallButton}
              >
                Следующий сезон
              </button>
            )}
          </div>
        )}
      </div>
      {loaded.status === "loading" && <p className="text-slate-600">Загружаем рейтинг…</p>}
      {loaded.status === "failed" && (
        <p role="alert" className="text-red-700">
          Не удалось загрузить рейтинг. Обновите страницу.
        </p>
      )}
      {rating &&
        (rating.players.length === 0 ? (
          <p className="text-sm text-slate-500">В этом сезоне ещё нет завершённых турниров</p>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table aria-label="Рейтинг клуба" className="w-full text-left">
              <thead className="bg-slate-50 text-sm text-slate-600">
                <tr>
                  <th scope="col" className="w-16 px-3 py-2 font-medium">
                    Место
                  </th>
                  <th scope="col" className="px-3 py-2 font-medium">
                    Игрок
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    Турниров
                  </th>
                  <th scope="col" className="px-3 py-2 text-right font-medium">
                    Очки
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {rating.players.map((row) => (
                  <tr key={row.player.id}>
                    <td className="px-3 py-2 font-medium text-slate-900">{row.position}</td>
                    <td className="px-3 py-2 text-slate-900">{row.player.name}</td>
                    <td className="px-3 py-2 text-right tabular-nums text-slate-600">
                      {row.tournaments}
                    </td>
                    <td className="px-3 py-2 text-right font-semibold tabular-nums text-slate-900">
                      {row.points}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ))}
    </section>
  );
}
