import { type FormEvent, useEffect, useId, useState } from "react";
import {
  type Club,
  correctPlace,
  fetchResults,
  RejectedError,
  type Tournament,
  type TournamentResult,
  type TournamentResults,
} from "./api";
import { startFormat } from "./dates";
import { inputClass, SERVER_UNREACHABLE, smallButton } from "./forms";
import { entries, pointsText } from "./points";

type Loaded =
  | { status: "loading" }
  | { status: "loaded"; results: TournamentResults }
  | { status: "failed" };

/** A finished tournament's places and rating points. A place entered by mistake is corrected
 * here, and everyone's points and the club rating are counted again. */
export default function ResultsPage({
  club,
  tournament,
  onBack,
}: {
  club: Club;
  tournament: Tournament;
  onBack: () => void;
}) {
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [editingPlayerId, setEditingPlayerId] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const headingId = useId();

  useEffect(() => {
    let stale = false;
    fetchResults(club.id, tournament.id)
      .then((results) => !stale && setLoaded({ status: "loaded", results }))
      .catch(() => !stale && setLoaded({ status: "failed" }));
    return () => {
      stale = true;
    };
  }, [club.id, tournament.id]);

  async function correct(result: TournamentResult, place: number) {
    const results = await correctPlace(club.id, tournament.id, result.player.id, place);
    setLoaded({ status: "loaded", results });
    setEditingPlayerId(null);
    setMessage(`${result.player.name}: ${place} место. Очки и рейтинг клуба пересчитаны.`);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-2xl bg-white p-6 shadow-sm">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{tournament.name}</h2>
          <p className="text-sm text-slate-600">
            {startFormat.format(new Date(tournament.starts_at))}
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

      <section aria-labelledby={headingId} className="rounded-2xl bg-white p-6 shadow-sm">
        <h3 id={headingId} className="mb-3 text-lg font-semibold text-slate-900">
          Результаты
        </h3>
        {loaded.status === "loading" && <p className="text-slate-600">Загружаем результаты…</p>}
        {loaded.status === "failed" && (
          <p role="alert" className="text-red-700">
            Не удалось загрузить результаты. Обновите страницу.
          </p>
        )}
        {message && (
          <p role="status" className="mb-3 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
            {message}
          </p>
        )}
        {loaded.status === "loaded" &&
          (loaded.results.results.length === 0 ? (
            <p className="text-sm text-slate-500">Результаты появятся, когда турнир завершится.</p>
          ) : (
            <ul
              aria-label="Результаты"
              className="divide-y divide-slate-200 rounded-xl border border-slate-200"
            >
              {loaded.results.results.map((result) => (
                <li
                  key={result.player.id}
                  aria-label={result.player.name}
                  className="flex flex-wrap items-center gap-x-3 gap-y-2 p-3"
                >
                  <span className="w-20 font-medium text-slate-900">{result.place} место</span>
                  <div className="min-w-32 flex-1">
                    <p className="text-slate-900">{result.player.name}</p>
                    {entries(result) && <p className="text-xs text-slate-500">{entries(result)}</p>}
                  </div>
                  <span className="font-medium tabular-nums text-slate-900">
                    {pointsText(result.points)}
                  </span>
                  {editingPlayerId === result.player.id ? (
                    <PlaceForm
                      result={result}
                      players={loaded.results.results.length}
                      primaryColor={club.primary_color}
                      save={(place) => correct(result, place)}
                      onClose={() => setEditingPlayerId(null)}
                    />
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setMessage("");
                        setEditingPlayerId(result.player.id);
                      }}
                      className={smallButton}
                    >
                      Исправить место
                    </button>
                  )}
                </li>
              ))}
            </ul>
          ))}
      </section>
    </div>
  );
}

function PlaceForm({
  result,
  players,
  primaryColor,
  save,
  onClose,
}: {
  result: TournamentResult;
  players: number;
  primaryColor: string;
  save: (place: number) => Promise<void>;
  onClose: () => void;
}) {
  const [place, setPlace] = useState(String(result.place));
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    setError("");
    try {
      await save(Number(place));
    } catch (failure) {
      setError(failure instanceof RejectedError ? failure.messages.join("\n") : SERVER_UNREACHABLE);
      setSaving(false);
    }
  }

  return (
    <form
      aria-label={`Место игрока ${result.player.name}`}
      onSubmit={submit}
      className="flex w-full flex-wrap items-center gap-2"
    >
      <label className="flex items-center gap-2 text-sm text-slate-700">
        Место
        <input
          type="number"
          min={1}
          max={players}
          required
          value={place}
          onChange={(event) => setPlace(event.target.value)}
          className={`${inputClass} w-24`}
        />
      </label>
      <button
        type="submit"
        disabled={saving}
        className="rounded-lg px-3 py-1 text-sm font-medium text-white"
        style={{ backgroundColor: primaryColor }}
      >
        Сохранить
      </button>
      <button type="button" onClick={onClose} className={smallButton}>
        Отмена
      </button>
      <p className="w-full text-xs text-slate-500">
        Игроки между старым и новым местом сдвинутся на одно место.
      </p>
      {error && (
        <p role="alert" className="w-full whitespace-pre-line text-sm text-red-700">
          {error}
        </p>
      )}
    </form>
  );
}
