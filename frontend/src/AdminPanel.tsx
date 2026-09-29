import { useState } from "react";
import type { Me } from "./api";
import LeagueBrand from "./LeagueBrand";
import PlayersPage from "./PlayersPage";
import RatingPage from "./RatingPage";
import ReportsPage from "./ReportsPage";
import TournamentsPage from "./TournamentsPage";

const SECTIONS = ["Турниры", "Игроки", "Рейтинг", "Отчёты"] as const;
type Section = (typeof SECTIONS)[number];

/** The club admin's workspace, dressed in the club's own logo and colours. The club's owner
 * works in it too, and alone sees the club's reports. */
export default function AdminPanel({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const { admin, club } = me;
  const [section, setSection] = useState<Section>("Турниры");
  const sections = SECTIONS.filter((name) => name !== "Отчёты" || admin.role === "owner");

  return (
    <>
      <header
        className="text-white shadow"
        style={{ backgroundColor: club.primary_color }}
      >
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-4 px-4 py-4">
          <img
            src={club.logo_url}
            alt={`Логотип: ${club.name}`}
            className="h-12 w-12 rounded-full bg-white p-1"
          />
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-xl font-semibold">{club.name}</h1>
            <p className="text-sm opacity-80">{admin.name}</p>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="rounded-lg px-4 py-2 font-medium text-slate-900"
            style={{ backgroundColor: club.accent_color }}
          >
            Выйти
          </button>
        </div>
        <div className="h-1" style={{ backgroundColor: club.accent_color }} />
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
        <nav aria-label="Разделы" className="mb-6 flex flex-wrap gap-2">
          {sections.map((name) => (
            <button
              key={name}
              type="button"
              aria-current={section === name ? "page" : undefined}
              onClick={() => setSection(name)}
              className={`rounded-lg px-4 py-2 font-medium ${
                section === name ? "text-white" : "bg-white text-slate-700 shadow-sm"
              }`}
              style={section === name ? { backgroundColor: club.primary_color } : undefined}
            >
              {name}
            </button>
          ))}
        </nav>
        {section === "Турниры" && <TournamentsPage club={club} />}
        {section === "Игроки" && <PlayersPage club={club} />}
        {section === "Рейтинг" && <RatingPage club={club} />}
        {section === "Отчёты" && <ReportsPage club={club} />}
        <LeagueBrand className="mt-8 justify-center text-slate-500" />
      </main>
    </>
  );
}
