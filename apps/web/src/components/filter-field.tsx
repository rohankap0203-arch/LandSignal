"use client";

import { useEffect, useId, useRef, useState } from "react";

export function HelpTip({
  title,
  body,
  tone = "hero",
}: {
  title: string;
  body: string;
  /** hero = search filters; panel = light intelligence pages */
  tone?: "hero" | "panel";
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const rootRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent | TouchEvent) => {
      const el = rootRef.current;
      if (!el) return;
      if (e.target instanceof Node && el.contains(e.target)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    // Defer so the opening click/tap does not immediately close.
    const t = window.setTimeout(() => {
      document.addEventListener("mousedown", onDoc);
      document.addEventListener("touchstart", onDoc, { passive: true });
    }, 0);
    window.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("touchstart", onDoc);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <span ref={rootRef} className={`help-tip tone-${tone}${open ? " is-open" : ""}`}>
      <button
        type="button"
        className={`help-tip-btn${open ? " on" : ""}`}
        aria-label={title}
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        ?
      </button>
      {open ? (
        <span id={id} role="tooltip" className="help-tip-pop">
          <strong>{title}</strong>
          <span>{body}</span>
        </span>
      ) : null}
    </span>
  );
}

export function FilterField({
  label,
  tip,
  children,
}: {
  label: string;
  tip?: { title: string; body: string };
  children: React.ReactNode;
}) {
  return (
    <div className={`filter-field${tip ? " has-tip" : ""}`}>
      <label>
        {label}
        {tip ? <HelpTip title={tip.title} body={tip.body} /> : null}
      </label>
      {children}
    </div>
  );
}

/** Preset select + optional custom typed value */
export function ComboFilter({
  label,
  tip,
  preset,
  presets,
  onPreset,
  custom,
  onCustom,
  customPlaceholder,
  showCustom,
  renderPresetLabel,
}: {
  label: string;
  tip?: { title: string; body: string };
  preset: string;
  presets: string[];
  onPreset: (v: string) => void;
  custom: string;
  onCustom: (v: string) => void;
  customPlaceholder?: string;
  showCustom?: boolean;
  renderPresetLabel?: (v: string) => string;
}) {
  const customMode =
    showCustom ?? (preset.toLowerCase().includes("custom") || preset === "__custom__");
  return (
    <FilterField label={label} tip={tip}>
      <select value={preset} onChange={(e) => onPreset(e.target.value)}>
        {presets.map((p) => (
          <option key={p} value={p}>
            {renderPresetLabel ? renderPresetLabel(p) : p}
          </option>
        ))}
      </select>
      {customMode ? (
        <input
          className="mt-1.5"
          value={custom}
          placeholder={customPlaceholder || "Type your own…"}
          onChange={(e) => onCustom(e.target.value)}
        />
      ) : null}
    </FilterField>
  );
}
