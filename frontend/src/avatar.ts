/**
 * The backend's `Player` carries an id and a name; the design wants an initial and a colour.
 * Derive both from the id so every client paints the same player the same way without the
 * server having to care about presentation.
 */

const COLORS = ["var(--yellow)", "var(--cyan)", "var(--lime)", "var(--pink)", "var(--white)"];

export interface Look {
  initial: string;
  color: string;
}

export function lookFor(player: { id: string; name: string }): Look {
  let h = 0;
  for (const ch of player.id) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return {
    initial: (player.name.trim()[0] ?? "?").toUpperCase(),
    color: COLORS[Math.abs(h) % COLORS.length],
  };
}
