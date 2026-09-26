import { useEffect, useState } from "react";
import AdminPanel from "./AdminPanel";
import { fetchMe, logout, type Me } from "./api";
import LoginPage from "./LoginPage";
import SystemStatus from "./SystemStatus";

type SessionState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "loggedIn"; me: Me };

export default function App() {
  const [session, setSession] = useState<SessionState>({ status: "loading" });

  function loadSession() {
    fetchMe()
      .then((me) => setSession(me ? { status: "loggedIn", me } : { status: "anonymous" }))
      .catch(() => setSession({ status: "anonymous" }));
  }

  useEffect(loadSession, []);

  function handleLogout() {
    // Only leave the panel once the server has dropped the session; otherwise it is still live.
    logout()
      .then(() => setSession({ status: "anonymous" }))
      .catch(() => window.alert("Не удалось выйти: нет связи с сервером. Попробуйте ещё раз."));
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-100">
      {session.status === "anonymous" && <LoginPage onLoggedIn={loadSession} />}
      {session.status === "loggedIn" && <AdminPanel me={session.me} onLogout={handleLogout} />}
      <footer className="p-4">
        <SystemStatus />
      </footer>
    </div>
  );
}
