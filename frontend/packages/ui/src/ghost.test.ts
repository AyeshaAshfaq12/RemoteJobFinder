import { describe, expect, it } from "vitest";
import { ghostBand } from "./ghost";

describe("ghostBand", () => {
  it.each([
    [0, "low"],
    [29, "low"],
    [30, "medium"],
    [59, "medium"],
    [60, "high"],
    [100, "high"],
  ] as const)("%i → %s", (score, band) => {
    expect(ghostBand(score)).toBe(band);
  });
});
