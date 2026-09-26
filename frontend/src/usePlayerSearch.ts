import { useCallback, useEffect, useState } from "react";
import { fetchPlayers, type Player } from "./api";

export type SearchState =
  | { status: "loading" }
  | { status: "loaded"; players: Player[] }
  | { status: "failed" };

/** The club's players matching `query`, fetched again whenever it changes or on `reload()`. */
export function usePlayerSearch(clubId: number, query: string) {
  const [state, setState] = useState<SearchState>({ status: "loading" });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    // Answers can arrive out of order while the admin types; only the latest one counts.
    let current = true;
    fetchPlayers(clubId, query)
      .then((players) => current && setState({ status: "loaded", players }))
      .catch(() => current && setState({ status: "failed" }));
    return () => {
      current = false;
    };
  }, [clubId, query, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { state, reload };
}
