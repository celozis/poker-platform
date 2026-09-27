/** Rating points in words: "1 очко", "3 очка", "10 очков", "21 очко". */
export function pointsText(points: number): string {
  const lastTwo = Math.abs(points) % 100;
  const last = lastTwo % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return `${points} очков`;
  if (last === 1) return `${points} очко`;
  if (last >= 2 && last <= 4) return `${points} очка`;
  return `${points} очков`;
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
