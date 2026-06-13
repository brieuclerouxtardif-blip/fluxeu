// Right-side sliding drawer that hosts the analytics panels (congestion now,
// Sankey / explorer / zone dashboard to come). Slides off-canvas when closed so
// the hero map stays unobstructed; scrolls internally when content overflows.

import type { ReactNode } from "react";

interface Props {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
}

export default function PanelDock({ open, title, subtitle, onClose, children }: Props) {
  return (
    <aside
      aria-hidden={!open}
      className={`absolute right-0 top-0 z-20 flex h-full w-[min(420px,calc(100vw-1rem))] flex-col border-l border-white/10 bg-surface-1/95 backdrop-blur transition-transform duration-300 ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <header className="flex items-center justify-between border-b border-white/10 px-4 py-3">
        <div>
          <h2 className="font-mono text-sm font-semibold tracking-tight text-accent">
            {title}
          </h2>
          {subtitle && <p className="text-[11px] text-slate-400">{subtitle}</p>}
        </div>
        <button
          onClick={onClose}
          className="flex h-7 w-7 items-center justify-center rounded text-slate-400 transition-colors hover:bg-white/5 hover:text-slate-200"
          title="Fermer"
          aria-label="Fermer le panneau"
        >
          ✕
        </button>
      </header>
      <div className="flex-1 overflow-y-auto px-4 py-4">{children}</div>
    </aside>
  );
}
