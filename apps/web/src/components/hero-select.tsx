"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

export type HeroSelectOption = {
  value: string;
  label: string;
};

type HeroSelectProps = {
  value: string;
  options: HeroSelectOption[];
  onChange: (value: string) => void;
  ariaLabel?: string;
  disabled?: boolean;
};

export function HeroSelect({
  value,
  options,
  onChange,
  ariaLabel,
  disabled,
}: HeroSelectProps) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const listId = useId();
  const selected = options.find((o) => o.value === value) || options[0];

  const close = useCallback(() => {
    setOpen(false);
    setActiveIndex(-1);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) close();
    };
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  useLayoutEffect(() => {
    if (!open) return;
    const idx = Math.max(
      0,
      options.findIndex((o) => o.value === value),
    );
    setActiveIndex(idx);
    listRef.current?.focus({ preventScroll: true });
    const el = listRef.current?.querySelector<HTMLElement>(`[data-idx="${idx}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [open, options, value]);

  function pick(next: string) {
    onChange(next);
    close();
  }

  function onTriggerKey(e: KeyboardEvent<HTMLButtonElement>) {
    if (disabled) return;
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setOpen(true);
    }
  }

  function onListKey(e: KeyboardEvent<HTMLUListElement>) {
    if (!options.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % options.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i <= 0 ? options.length - 1 : i - 1));
    } else if (e.key === "Home") {
      e.preventDefault();
      setActiveIndex(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActiveIndex(options.length - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const opt = options[activeIndex];
      if (opt) pick(opt.value);
    } else if (e.key === "Escape") {
      e.preventDefault();
      close();
    }
  }

  return (
    <div className={`hero-select${open ? " is-open" : ""}`} ref={rootRef}>
      <button
        type="button"
        className="hero-select-trigger"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={onTriggerKey}
      >
        <span className="hero-select-value">{selected?.label || "Any"}</span>
        <span className="hero-select-chevron" aria-hidden>
          ▾
        </span>
      </button>
      {open ? (
        <ul
          ref={listRef}
          id={listId}
          className="hero-select-menu"
          role="listbox"
          tabIndex={-1}
          aria-activedescendant={
            activeIndex >= 0 ? `${listId}-opt-${activeIndex}` : undefined
          }
          onKeyDown={onListKey}
        >
          {options.map((opt, idx) => {
            const isSelected = opt.value === value;
            const isActive = idx === activeIndex;
            return (
              <li key={opt.value} role="presentation">
                <button
                  type="button"
                  id={`${listId}-opt-${idx}`}
                  data-idx={idx}
                  role="option"
                  aria-selected={isSelected}
                  className={`hero-select-option${isSelected ? " is-selected" : ""}${
                    isActive ? " is-active" : ""
                  }`}
                  onMouseEnter={() => setActiveIndex(idx)}
                  onClick={() => pick(opt.value)}
                >
                  <span>{opt.label}</span>
                  {isSelected ? <span className="hero-select-check" aria-hidden>✓</span> : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}
