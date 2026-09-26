import type { TournamentStatus } from "./api";

/** A tournament's state as the admin reads it. */
export const STATUS_NAMES: Record<TournamentStatus, string> = {
  scheduled: "Создан",
  running: "Идёт",
  paused: "Пауза",
  finished: "Завершён",
  cancelled: "Отменён",
};
