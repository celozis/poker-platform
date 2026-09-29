import { useEffect, useRef } from "react";
import { tournamentSocketUrl } from "./api";
import { reconnectDelay } from "./sockets";

// The server's refusal: not the admin's club, or the admin is logged out. Trying again won't help.
const NO_ACCESS = 4403;

/**
 * Calls `onChange` whenever the tournament changes on the server, whoever changed it: another
 * admin, or a player in the Telegram bot. The server only says "changed" over a WebSocket; the
 * page reads what it shows afresh. A lost connection is made again, and then the page reads
 * afresh too, as changes made meanwhile were not heard.
 */
export function useTournamentChanges(clubId: number, tournamentId: number, onChange: () => void) {
  // The latest callback, so a new one does not make a new connection.
  const changed = useRef(onChange);
  changed.current = onChange;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    let stopped = false;

    function connect(again: boolean) {
      socket = new WebSocket(tournamentSocketUrl(clubId, tournamentId));
      socket.onopen = () => {
        failures = 0;
        if (again) changed.current();
      };
      socket.onmessage = () => changed.current();
      socket.onclose = (event: CloseEvent) => {
        if (stopped || event.code === NO_ACCESS) return;
        retry = setTimeout(() => connect(true), reconnectDelay(failures++));
      };
    }

    connect(false);
    return () => {
      stopped = true;
      clearTimeout(retry);
      socket?.close();
    };
  }, [clubId, tournamentId]);
}
