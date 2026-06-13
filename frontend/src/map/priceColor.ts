// Day-ahead price -> RGB ramp for the live map.
//
// Hard rule (PLAN §9 / CLAUDE.md): negative prices are normal and must read as
// DISTINCT, not clipped. So the ramp is two regimes joined at 0 €/MWh:
//   - negative  -> cold, saturated blues/indigo (the "teinte froide saturée")
//   - positive  -> teal -> lime -> yellow -> orange -> red -> magenta (heat)
// Linear interpolation between explicit anchor stops, in sRGB (good enough for
// a categorical-ish legend; we are not doing perceptual color science here).

type Stop = [eurMwh: number, rgb: [number, number, number]];

const STOPS: Stop[] = [
  [-100, [79, 70, 229]], // indigo — deep negative
  [-20, [56, 189, 248]], // sky blue — mild negative
  [0, [45, 212, 191]], // teal — free / near zero
  [40, [163, 230, 53]], // lime
  [80, [250, 204, 21]], // yellow
  [140, [249, 115, 22]], // orange
  [250, [239, 68, 68]], // red
  [600, [217, 70, 239]], // magenta — extreme spike
];

function lerp(a: number, b: number, t: number): number {
  return Math.round(a + (b - a) * t);
}

/** Map a price (€/MWh) to an [r,g,b] triple along the ramp above. */
export function priceColor(eurMwh: number): [number, number, number] {
  if (eurMwh <= STOPS[0][0]) return STOPS[0][1];
  const last = STOPS[STOPS.length - 1];
  if (eurMwh >= last[0]) return last[1];
  for (let i = 0; i < STOPS.length - 1; i++) {
    const [p0, c0] = STOPS[i];
    const [p1, c1] = STOPS[i + 1];
    if (eurMwh >= p0 && eurMwh <= p1) {
      const t = (eurMwh - p0) / (p1 - p0);
      return [lerp(c0[0], c1[0], t), lerp(c0[1], c1[1], t), lerp(c0[2], c1[2], t)];
    }
  }
  return last[1];
}

/** CSS `linear-gradient(...)` string for the legend bar, low €/MWh -> high. */
export function priceRampCss(): string {
  const lo = STOPS[0][0];
  const hi = STOPS[STOPS.length - 1][0];
  const span = hi - lo;
  const parts = STOPS.map(([p, [r, g, b]]) => {
    const pct = ((p - lo) / span) * 100;
    return `rgb(${r},${g},${b}) ${pct.toFixed(1)}%`;
  });
  return `linear-gradient(to right, ${parts.join(", ")})`;
}
