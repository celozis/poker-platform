import { describe, expect, it } from "vitest";
import type { StructureItem } from "./api";
import { next, untilBreak } from "./blindClock";

const level = (minutes: number): StructureItem => ({
  kind: "level",
  small_blind: 100,
  big_blind: 200,
  ante: 0,
  duration_minutes: minutes,
});
const pause = (minutes: number): StructureItem => ({ kind: "break", duration_minutes: minutes });

describe("time until the next break", () => {
  const structure = [level(20), level(15), pause(10), level(20), pause(5), level(20)];

  it("adds up what is left of this level and the whole levels before the break", () => {
    expect(untilBreak(structure, 0, 300)).toBe(300 + 15 * 60);
    expect(untilBreak(structure, 1, 42)).toBe(42);
  });

  it("looks past the break being played to the one after it", () => {
    expect(untilBreak(structure, 2, 120)).toBe(120 + 20 * 60);
  });

  it("is null when no break is left", () => {
    expect(untilBreak(structure, 4, 60)).toBeNull();
    expect(untilBreak(structure, 5, 600)).toBeNull();
  });
});

describe("what comes next", () => {
  const structure: StructureItem[] = [
    level(20),
    pause(10),
    { kind: "level", small_blind: 300, big_blind: 600, ante: 75, duration_minutes: 20 },
  ];

  it("names the level after a coming break too", () => {
    expect(next(structure, 0)).toBe("Дальше: перерыв 10 мин, потом уровень 2 · 300 / 600, анте 75");
  });

  it("names the next level", () => {
    expect(next(structure, 1)).toBe("Дальше: уровень 2 · 300 / 600, анте 75");
  });
});
