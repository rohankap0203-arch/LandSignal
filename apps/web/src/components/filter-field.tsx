"use client";

import { useId, useState } from "react";

export function HelpTip({ title, body }: { title: string; body: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="help-tip">
      <button
        type="button"
        className="help-tip-btn"
        aria-describedby={open ? id : undefined}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        onBlur={() => setOpen(false)}
      >
        ?
      </button>
      {open && (
        <span id={id} role="tooltip" className="help-tip-pop">
          <strong>{title}</strong>
          <span>{body}</span>
        </span>
      )}
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
    <div className="filter-field">
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
  const customMode = showCustom ?? (preset.toLowerCase().includes("custom") || preset === "__custom__");
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
