/** A count with the word in the form Russian puts after it: `forms` for 1, 2 and 5, such as
 * ["очко", "очка", "очков"] for "1 очко", "3 очка", "10 очков", "21 очко". */
function counted(count: number, forms: [string, string, string]): string {
  const lastTwo = Math.abs(count) % 100;
  const last = lastTwo % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return `${count} ${forms[2]}`;
  if (last === 1) return `${count} ${forms[0]}`;
  if (last >= 2 && last <= 4) return `${count} ${forms[1]}`;
  return `${count} ${forms[2]}`;
}

/** Rating points in words: "1 очко", "3 очка", "10 очков", "21 очко". */
export function pointsText(points: number): string {
  return counted(points, ["очко", "очка", "очков"]);
}

/** "1 турнир", "2 турнира", "5 турниров". */
export function tournamentsText(tournaments: number): string {
  return counted(tournaments, ["турнир", "турнира", "турниров"]);
}

/** What a player bought during the tournament, e.g. "re-entry: 1, add-on: 2". */
export function entries(player: { reentries: number; addons: number }): string {
  return [
    player.reentries > 0 && `re-entry: ${player.reentries}`,
    player.addons > 0 && `add-on: ${player.addons}`,
  ]
    .filter(Boolean)
    .join(", ");
}
