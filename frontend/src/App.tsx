import { useEffect, useState } from "react";

// Mirrors the Health response model of GET /api/health in backend/app/main.py.
type Health = { api: "ok"; database: "ok" | "unavailable" };

type HealthState =
  | { status: "loading" }
  | { status: "loaded"; health: Health }
  | { status: "unreachable" };

async function fetchHealth(): Promise<Health> {
  const response = await fetch("/api/health");
  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`);
  }
  return response.json();
}

export default function App() {
  const [state, setState] = useState<HealthState>({ status: "loading" });

  useEffect(() => {
    fetchHealth()
      .then((health) => setState({ status: "loaded", health }))
      .catch(() => setState({ status: "unreachable" }));
  }, []);

  return (
    <main>
      <h1>Сибирская лига покера</h1>
      {state.status === "loading" && <p>Проверяем систему…</p>}
      {state.status === "unreachable" && <p>API недоступен</p>}
      {state.status === "loaded" && (
        <ul>
          {state.health.api === "ok" && <li>API работает</li>}
          <li>
            {state.health.database === "ok"
              ? "База данных доступна"
              : "База данных недоступна"}
          </li>
        </ul>
      )}
    </main>
  );
}
