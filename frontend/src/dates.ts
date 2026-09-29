/** A tournament's start as the admin reads it, e.g. "пт, 2 октября, 19:00". */
export const startFormat = new Intl.DateTimeFormat("ru-RU", {
  weekday: "short",
  day: "numeric",
  month: "long",
  hour: "2-digit",
  minute: "2-digit",
});

/** The day a tournament was played, e.g. "26 сентября 2026 г.". */
export const dayFormat = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

/** A day of the browser's calendar as a date input's value, "2026-09-01". */
export function isoDay(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

/** "01.09" of "2026-09-01". */
export function dayMonth(day: string): string {
  return `${day.slice(8, 10)}.${day.slice(5, 7)}`;
}
