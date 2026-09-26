import type { Me } from "./api";
import LeagueBrand from "./LeagueBrand";
import TournamentsPage from "./TournamentsPage";

/** The club admin's workspace, dressed in the club's own logo and colours. */
export default function AdminPanel({ me, onLogout }: { me: Me; onLogout: () => void }) {
  const { admin, club } = me;

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
        <TournamentsPage club={club} />
        <LeagueBrand className="mt-8 justify-center text-slate-500" />
      </main>
    </>
  );
}
