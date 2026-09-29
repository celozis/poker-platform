/** The address of a WebSocket on this site's backend, secure when the page is. */
export function socketUrl(path: string): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}${path}`;
}

// A lost connection is tried again soon, then less often while the server stays away.
const RECONNECT_DELAYS_MS = [1000, 2000, 5000, 10000];

/** How long to wait before connecting again after this many failures in a row. */
export function reconnectDelay(failures: number): number {
  return RECONNECT_DELAYS_MS[Math.min(failures, RECONNECT_DELAYS_MS.length - 1)];
}
