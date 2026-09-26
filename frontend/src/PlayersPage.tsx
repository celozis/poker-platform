import { useState } from "react";
import { addPlayer, type Club } from "./api";
import { inputClass } from "./forms";
import { formatPhone } from "./phones";
import PlayerForm, { addedMessage } from "./PlayerForm";
import { usePlayerSearch } from "./usePlayerSearch";

/** The club's own list of players: search it and add new players. */
export default function PlayersPage({ club }: { club: Club }) {
  const [query, setQuery] = useState("");
  const [message, setMessage] = useState("");
  const { state, reload } = usePlayerSearch(club.id, query);

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="new-player" className="rounded-2xl bg-white p-6 shadow-sm">
        <h2 id="new-player" className="mb-4 text-lg font-semibold text-slate-900">
          Новый игрок
        </h2>
        <PlayerForm
          primaryColor={club.primary_color}
          submitLabel="Добавить игрока"
          add={async (input) => {
            setMessage("");
            const added = await addPlayer(club.id, input);
            setMessage(addedMessage(added));
            reload();
          }}
        />
        {message && (
          <p role="status" className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
            {message}
          </p>
        )}
      </section>

      <section aria-labelledby="club-players" className="rounded-2xl bg-white p-6 shadow-sm">
        <h2 id="club-players" className="mb-4 text-lg font-semibold text-slate-900">
          Игроки клуба
        </h2>
        <input
          type="search"
          aria-label="Поиск по имени или телефону"
          placeholder="Поиск по имени или телефону"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className={`${inputClass} mb-4 w-full`}
        />
        {state.status === "loading" && <p className="text-slate-600">Загружаем игроков…</p>}
        {state.status === "failed" && (
          <p role="alert" className="text-red-700">
            Не удалось загрузить игроков. Обновите страницу.
          </p>
        )}
        {state.status === "loaded" &&
          (state.players.length === 0 ? (
            <p className="text-sm text-slate-500">
              {query.trim() ? "Никого не нашли" : "В клубе пока нет игроков"}
            </p>
          ) : (
            <ul
              aria-label="Игроки клуба"
              className="divide-y divide-slate-200 rounded-xl border border-slate-200"
            >
              {state.players.map((player) => (
                <li
                  key={player.id}
                  aria-label={player.name}
                  className="flex flex-wrap justify-between gap-x-4 p-3"
                >
                  <span className="font-medium text-slate-900">{player.name}</span>
                  <span className="text-slate-600">{formatPhone(player.phone)}</span>
                </li>
              ))}
            </ul>
          ))}
      </section>
    </div>
  );
}
