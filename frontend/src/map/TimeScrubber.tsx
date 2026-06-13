// 48 h time scrubber (PLAN §4.1). The playhead runs on a requestAnimationFrame
// loop and updates the slider thumb + time label *imperatively* (refs) — React
// state changes only when the floored frame index crosses an hour. That keeps
// the thumb at 60 fps while the map re-renders at most once per data-hour
// (stepped), avoiding a per-frame React/deck.gl re-render storm.

import { useEffect, useRef, useState } from "react";
import type { HistoryFrame } from "../types";

// playback speed = data-hours advanced per real second
const SPEEDS = [2, 4, 8] as const;

interface Props {
  frames: HistoryFrame[]; // ascending by ts
  live: boolean; // true = App is showing the live snapshot
  onScrub: (index: number) => void; // user/playhead selected a past frame
  onLive: () => void; // return to live
  format: (d: Date) => string; // Europe/Brussels formatter
}

export default function TimeScrubber({ frames, live, onScrub, onLive, format }: Props) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<number>(4);

  const sliderRef = useRef<HTMLInputElement>(null);
  const labelRef = useRef<HTMLSpanElement>(null);
  const playheadRef = useRef(0); // ms (epoch)
  const rafRef = useRef(0);
  const lastTickRef = useRef(0);
  const lastIdxRef = useRef(-1);

  const times = frames.map((f) => new Date(f.ts).getTime());
  const t0 = times.length ? times[0] : 0;
  const t1 = times.length ? times[times.length - 1] : 0;
  const span = Math.max(1, t1 - t0);

  // frame index at-or-before a playhead time (step / floor — never interpolate)
  const indexAt = (ms: number): number => {
    let lo = 0;
    let hi = times.length - 1;
    let ans = 0;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (times[mid] <= ms) {
        ans = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    return ans;
  };

  const paint = (ms: number) => {
    if (sliderRef.current) sliderRef.current.value = String(((ms - t0) / span) * 1000);
    if (labelRef.current) labelRef.current.textContent = format(new Date(ms));
  };

  // play loop
  useEffect(() => {
    if (!playing || frames.length === 0) return;
    lastTickRef.current = performance.now();
    const tick = (now: number) => {
      const dt = (now - lastTickRef.current) / 1000;
      lastTickRef.current = now;
      let ph = playheadRef.current + speed * 3_600_000 * dt;
      if (ph >= t1) ph = t0; // loop the window (vitrine)
      playheadRef.current = ph;
      paint(ph);
      const idx = indexAt(ph);
      if (idx !== lastIdxRef.current) {
        lastIdxRef.current = idx;
        onScrub(idx);
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing, speed, frames, t0, t1, span]);

  // when App returns to live, park the thumb at the end and badge it LIVE
  useEffect(() => {
    if (live) {
      playheadRef.current = t1;
      lastIdxRef.current = frames.length - 1;
      if (sliderRef.current) sliderRef.current.value = "1000";
      if (labelRef.current) labelRef.current.textContent = "● LIVE";
    }
  }, [live, t1, frames.length]);

  if (frames.length === 0) return null;

  const onInput = (e: React.FormEvent<HTMLInputElement>) => {
    const ms = t0 + (Number(e.currentTarget.value) / 1000) * span;
    playheadRef.current = ms;
    if (labelRef.current) labelRef.current.textContent = format(new Date(ms));
    const idx = indexAt(ms);
    if (idx !== lastIdxRef.current) {
      lastIdxRef.current = idx;
      onScrub(idx);
    }
  };

  const startPlay = () => {
    if (live) {
      // begin a fresh replay of the window
      playheadRef.current = t0;
      lastIdxRef.current = -1;
      onScrub(0);
    }
    setPlaying(true);
  };

  return (
    <div className="pointer-events-auto absolute bottom-4 left-1/2 z-10 w-[min(640px,calc(100vw-2rem))] -translate-x-1/2 rounded-lg border border-white/10 bg-surface-1/85 px-4 py-3 font-mono text-xs text-slate-300 backdrop-blur">
      <div className="flex items-center gap-3">
        <button
          onClick={() => (playing ? setPlaying(false) : startPlay())}
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-accent/20 text-accent transition-colors hover:bg-accent/30"
          title={playing ? "Pause" : "Lecture (rejoue 48 h)"}
        >
          {playing ? "❚❚" : "▶"}
        </button>

        <input
          ref={sliderRef}
          type="range"
          min={0}
          max={1000}
          step={1}
          defaultValue={1000}
          onPointerDown={() => setPlaying(false)}
          onInput={onInput}
          className="h-1 flex-1 cursor-pointer appearance-none rounded bg-slate-600 accent-accent"
          aria-label="time scrubber (48 h)"
        />

        <span
          ref={labelRef}
          className="w-32 shrink-0 text-right tabular-nums text-slate-200"
        >
          ● LIVE
        </span>
      </div>

      <div className="mt-2 flex items-center justify-between text-[10px] text-slate-500">
        <div className="flex items-center gap-1">
          <span className="mr-1">vitesse</span>
          {SPEEDS.map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              className={`rounded px-1.5 py-0.5 transition-colors ${
                speed === s ? "bg-accent/20 text-accent" : "text-slate-500 hover:text-slate-300"
              }`}
              title={`${s} heures de données par seconde`}
            >
              {s}h/s
            </button>
          ))}
        </div>
        <button
          onClick={() => {
            setPlaying(false);
            onLive();
          }}
          disabled={live}
          className={`rounded px-2 py-0.5 transition-colors ${
            live
              ? "text-emerald-400"
              : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
          }`}
          title="Revenir au temps réel"
        >
          {live ? "● temps réel" : "↩ revenir au live"}
        </button>
      </div>
    </div>
  );
}
