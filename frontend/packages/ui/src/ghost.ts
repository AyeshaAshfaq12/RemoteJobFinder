export type GhostBand = "low" | "medium" | "high";

/** Same banding as the server (Build Spec §7): 0–29 low, 30–59 medium, 60+ high. */
export function ghostBand(score: number): GhostBand {
  if (score < 30) return "low";
  if (score < 60) return "medium";
  return "high";
}
