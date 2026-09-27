import { useEffect, useState } from "react";
import type { BlindLevel, Clock, StructureItem } from "./api";

// Shared by the admin panel and the hall board, so that both show the clock the same way.

export const numberFormat = new Intl.NumberFormat("ru-RU");

/** "200 / 400". */
export function blinds(level: BlindLevel): string {
  return `${numberFormat.format(level.small_blind)} / ${numberFormat.format(level.big_blind)}`;
}

/** "Уровень 2" and "200 / 400, анте 50", or "Перерыв" with no blinds. */
export function describe(structure: StructureItem[], index: number): { name: string; blinds: string } {
  const item = structure[index];
  if (item.kind === "break") return { name: "Перерыв", blinds: "" };
  const level = structure.slice(0, index + 1).filter((i) => i.kind === "level").length;
  const text = blinds(item);
  return {
    name: `Уровень ${level}`,
    blinds: item.ante > 0 ? `${text}, анте ${numberFormat.format(item.ante)}` : text,
  };
}

/** What comes after the item being played; after a break, also the level that follows it. */
export function next(structure: StructureItem[], index: number): string {
  if (index + 1 >= structure.length) return "Последний уровень структуры";
  const level = (at: number) => {
    const { name, blinds } = describe(structure, at);
    return `${name.toLowerCase()} · ${blinds}`;
  };
  const item = structure[index + 1];
  if (item.kind === "level") return `Дальше: ${level(index + 1)}`;
  const pause = `Дальше: перерыв ${item.duration_minutes} мин`;
  const after = structure.findIndex((later, at) => at > index + 1 && later.kind === "level");
  return after === -1 ? pause : `${pause}, потом ${level(after)}`;
}

/** Seconds until the next break starts: what is left of the item being played and every level
 * after it up to the break. Past the break being played; null when no break is left. */
export function untilBreak(
  structure: StructureItem[],
  index: number,
  secondsLeft: number,
): number | null {
  let seconds = secondsLeft;
  for (const item of structure.slice(index + 1)) {
    if (item.kind === "break") return seconds;
    seconds += item.duration_minutes * 60;
  }
  return null;
}

const pad = (value: number) => String(value).padStart(2, "0");

/** "04:05", or "1:04:05" from an hour up. */
export function formatTime(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const clock = `${pad(minutes)}:${pad(seconds % 60)}`;
  return hours > 0 ? `${hours}:${clock}` : clock;
}

// Often enough for every screen to turn to the next second within a quarter of a second.
const TICK_MS = 250;
// How soon the server is asked again when the question at an item's end went unanswered.
const ASK_AGAIN_MS = 2000;

/**
 * Whole seconds left of the item being played, counted down in the browser from what the server
 * said and when it said it (`receivedAt`). Every screen counts to the same end moment, to the
 * millisecond, so the admin panel and the hall board turn over together. When the item's time is
 * up and another one follows, `onItemOver` is called, and again every few seconds until a new
 * clock comes: only the server knows what comes next.
 */
export function useCountdown(
  structure: StructureItem[],
  clock: Clock,
  receivedAt: number,
  onItemOver: () => void,
): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    setNow(Date.now());
    if (!clock.running) return;
    const timer = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(timer);
  }, [clock.running, receivedAt]);

  // `now` can be older than a clock that has just come, until the next tick.
  const elapsed = clock.running ? Math.max(0, now - receivedAt) : 0;
  const msLeft = Math.round(clock.seconds_left * 1000) - elapsed;
  const secondsLeft = Math.max(0, Math.ceil(msLeft / 1000));
  const isLast = clock.item >= structure.length - 1;
  const itemOver = clock.running && clock.seconds_left > 0 && secondsLeft === 0 && !isLast;

  useEffect(() => {
    if (!itemOver) return;
    onItemOver();
    const askAgain = setInterval(onItemOver, ASK_AGAIN_MS);
    return () => clearInterval(askAgain);
  }, [itemOver, onItemOver]);

  return secondsLeft;
}
