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
