import { vi } from "vitest";
import type { BoardState } from "../api";

/** A stand-in for the browser's WebSocket: the test opens it, sends it boards and drops it. */
export class FakeWebSocket {
  static sockets: FakeWebSocket[] = [];

  url: string;
  closedByPage = false;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.sockets.push(this);
  }

  close() {
    this.closedByPage = true;
  }

  /** The server accepts the connection and sends the board as it is now. */
  open(board: BoardState) {
    this.onopen?.();
    this.send(board);
  }

  /** The server sends the board after a change. */
  send(board: BoardState) {
    this.onmessage?.({ data: JSON.stringify(board) });
  }

  /** The connection is lost: the network went down or the backend restarted. */
  drop() {
    this.onclose?.({ code: 1006 });
  }

  /** The server has no board with this code: it accepts the connection and closes it so. */
  refuse() {
    this.onclose?.({ code: 4404 });
  }
}

/** Replaces the browser's WebSocket; returns the sockets the page opens, in order. */
export function fakeWebSockets(): FakeWebSocket[] {
  FakeWebSocket.sockets = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
  return FakeWebSocket.sockets;
}
