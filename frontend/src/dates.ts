/** A tournament's start as the admin reads it, e.g. "пт, 2 октября, 19:00". */
export const startFormat = new Intl.DateTimeFormat("ru-RU", {
  weekday: "short",
  day: "numeric",
  month: "long",
  hour: "2-digit",
  minute: "2-digit",
});
