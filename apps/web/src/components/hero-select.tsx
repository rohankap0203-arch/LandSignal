"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";

export type HeroSelectOption = {
  value: string;
  label: string;
};

type HeroSelectBase = {
  options: HeroSelectOption[];
  ariaLabel?: string;
  disabled?: boolean;
};

type HeroSelectSingleProps = HeroSelectBase & {
  multi?: false;
  value: string;
  onChange: (value: string) => void;
};

type HeroSelectMultiProps = HeroSelectBase & {
  multi: true;
  values: string[];
  onChange: (values: string[]) => void;
};

export type HeroSelectProps = HeroSelectSingleProps | HeroSelectMultiProps;

function isAnyValue(v: string) {
  return !v || v === "Any";
}

function selectedSet(multi: boolean, value: string | undefined, values: string[] | undefined): Set<string> {
  if (multi) {
    const list = (values || []).filter((v) => !isAnyValue(v));
    return new Set(list);
  }
  if (!value || isAnyValue(value)) return new Set();
  return new Set([value]);
}

function displayLabel(
  multi: boolean,
  options: HeroSelectOption[],
  value: string | undefined,
  values: string[] | undefined,
): string {
  if (!multi) {
    return options.find((o) => o.value === value)?.label || value || "Any";
  }
  const picked = (values || []).filter((v) => !isAnyValue(v));
  if (!picked.length) return "Any";
  const labels = picked.map((v) => options.find((o) => o.value === v)?.label || v);
  if (labels.length === 1) return labels[0];
  if (labels.length === 2) return `${labels[0]}, ${labels[1]}`;
  return `${labels[0]} +${labels.length - 1}`;
}

/** Scroll an option inside the menu only — never call Element.scrollIntoView (that moves the page). */
function scrollOptionIntoMenu(menu: HTMLElement, option: HTMLElement) {
  const optionTop = option.offsetTop;
  const optionBottom = optionTop + option.offsetHeight;
  const viewTop = menu.scrollTop;
  const viewBottom = viewTop + menu.clientHeight;
  if (optionTop < viewTop) {
    menu.scrollTop = optionTop;
  } else if (optionBottom > viewBottom) {
    menu.scrollTop = optionBottom - menu.clientHeight;
  }
}

export function HeroSelect(props: HeroSelectProps) {
  const { options, ariaLabel, disabled } = props;
  const multi = Boolean(props.multi);
  const value = multi ? undefined : (props as HeroSelectSingleProps).value;
  const values = multi ? (props as HeroSelectMultiProps).values : undefined;

  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const rootRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const wasOpenRef = useRef(false);
  const listId = useId();

  const selected = useMemo(
    () => selectedSet(multi, value, values),
    [multi, value, values],
  );
  const label = displayLabel(multi, options, value, values);

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

  // Only when the menu opens — not on every meta poll / value toggle (those re-created
  // `options` arrays and used scrollIntoView, which yanked the page/menu back to the top).
  useLayoutEffect(() => {
    if (!open) {
      wasOpenRef.current = false;
      return;
    }
    const justOpened = !wasOpenRef.current;
    wasOpenRef.current = true;
    if (!justOpened) return;

    const current = multi
      ? (values || []).find((v) => !isAnyValue(v)) || "Any"
      : value || "Any";
    const idx = Math.max(
      0,
      options.findIndex((o) => o.value === current),
    );
    setActiveIndex(idx);
    const menu = listRef.current;
    menu?.focus({ preventScroll: true });
    const el = menu?.querySelector<HTMLElement>(`[data-idx="${idx}"]`);
    if (menu && el) scrollOptionIntoMenu(menu, el);
  }, [open, options, value, values, multi]);

  function emitSingle(next: string) {
    (props as HeroSelectSingleProps).onChange(next);
    close();
  }

  function emitMulti(next: string[]) {
    const cleaned = next.filter((v) => !isAnyValue(v));
    (props as HeroSelectMultiProps).onChange(cleaned.length ? cleaned : ["Any"]);
  }

  function pick(next: string) {
    if (!multi) {
      emitSingle(next);
      return;
    }
    if (isAnyValue(next)) {
      emitMulti([]);
      close();
      return;
    }
    const nextSet = new Set(selected);
    if (nextSet.has(next)) nextSet.delete(next);
    else nextSet.add(next);
    emitMulti([...nextSet]);
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
    const move = (next: number) => {
      setActiveIndex(next);
      requestAnimationFrame(() => {
        const menu = listRef.current;
        const el = menu?.querySelector<HTMLElement>(`[data-idx="${next}"]`);
        if (menu && el) scrollOptionIntoMenu(menu, el);
      });
    };
    if (e.key === "ArrowDown") {
      e.preventDefault();
      move((activeIndex + 1) % options.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      move(activeIndex <= 0 ? options.length - 1 : activeIndex - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      move(0);
    } else if (e.key === "End") {
      e.preventDefault();
      move(options.length - 1);
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
    <div className={`hero-select${open ? " is-open" : ""}${multi ? " is-multi" : ""}`} ref={rootRef}>
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
        <span className="hero-select-value">{label}</span>
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
          aria-multiselectable={multi || undefined}
          aria-activedescendant={
            activeIndex >= 0 ? `${listId}-opt-${activeIndex}` : undefined
          }
          onKeyDown={onListKey}
        >
          {options.map((opt, idx) => {
            const isSelected = isAnyValue(opt.value)
              ? selected.size === 0
              : selected.has(opt.value);
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
