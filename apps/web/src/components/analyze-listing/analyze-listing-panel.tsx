"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { landsignalApi, type UrlAnalyzeResult } from "@/lib/api";

const STAGE_ORDER = [
  "reading_listing",
  "identifying_property",
  "resolving_parcel",
  "verifying_property_data",
  "enriching_location",
  "evaluating_market",
  "modeling_value",
  "evaluating_risk",
  "calculating_opportunity",
  "building_report",
] as const;

type Phase = "idle" | "processing" | "confirm" | "fallback" | "done";

function isValidHttpUrl(raw: string): boolean {
  try {
    const u = new URL(raw.trim());
    return u.protocol === "http:" || u.protocol === "https:";
  } catch {
    return false;
  }
}

function draftStr(draft: Record<string, unknown> | undefined, key: string): string {
  const v = draft?.[key];
  if (v == null || v === "") return "";
  return String(v);
}

function LandLoadingVisual({ active }: { active: boolean }) {
  return (
    <div className={`analyze-land-visual${active ? " is-active" : ""}`} aria-hidden>
      <div className="analyze-land-sky" />
      <div className="analyze-land-haze" />
      <svg className="analyze-land-svg" viewBox="0 0 320 120" preserveAspectRatio="none">
        <defs>
          <linearGradient id="analyzeLandFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8fa887" stopOpacity="0.95" />
            <stop offset="55%" stopColor="#6f8a68" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#4f6a4a" stopOpacity="0.85" />
          </linearGradient>
        </defs>
        <path
          className="analyze-land-ridge analyze-land-ridge-a"
          d="M0 78 C40 62 70 90 110 70 C150 50 180 86 220 64 C260 44 290 72 320 58 L320 120 L0 120 Z"
          fill="url(#analyzeLandFill)"
        />
        <path
          className="analyze-land-ridge analyze-land-ridge-b"
          d="M0 92 C50 80 90 104 140 88 C190 72 230 100 270 86 C295 78 310 90 320 84 L320 120 L0 120 Z"
          fill="#5d7a56"
          opacity="0.72"
        />
        <path
          className="analyze-land-parcel"
          d="M118 54 L188 48 L204 86 L132 94 Z"
          fill="rgba(214,162,67,0.28)"
          stroke="#d6a243"
          strokeWidth="2"
        />
      </svg>
      <div className="analyze-land-scan" />
    </div>
  );
}

export function AnalyzeListingPanel() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<UrlAnalyzeResult | null>(null);
  const [visibleStageIdx, setVisibleStageIdx] = useState(0);
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) closeModal();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [open, busy]);

  const stages = result?.stages || [];
  const doneStages = useMemo(
    () => stages.filter((s) => s.status === "done" || s.status === "error"),
    [stages],
  );

  useEffect(() => {
    if (phase !== "processing" && phase !== "confirm" && phase !== "done" && phase !== "fallback") {
      return;
    }
    if (doneStages.length === 0) return;
    setVisibleStageIdx(0);
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setVisibleStageIdx(Math.min(i, doneStages.length));
      if (i >= doneStages.length) window.clearInterval(id);
    }, 260);
    return () => window.clearInterval(id);
  }, [phase, doneStages.length, result?.parcel_id]);

  function closeModal() {
    if (busy) return;
    setOpen(false);
    setPhase("idle");
    setResult(null);
    setUrlError("");
  }

  function seedCorrections(res: UrlAnalyzeResult) {
    const draft = res.draft || {};
    const seed: Record<string, string> = {
      title: draftStr(draft, "title"),
      state: draftStr(draft, "state"),
      county: draftStr(draft, "county"),
      acreage: draftStr(draft, "acreage"),
      asking_price_usd: draftStr(draft, "asking_price_usd"),
      address: draftStr(draft, "address"),
      apn: draftStr(draft, "apn"),
      coordinates:
        draft.latitude != null && draft.longitude != null
          ? `${draft.latitude}, ${draft.longitude}`
          : "",
    };
    for (const m of res.missing_material || []) {
      if (!(m.field in seed)) seed[m.field] = "";
    }
    setCorrections(seed);
  }

  async function runAnalyze(extra?: Record<string, string>) {
    const trimmed = url.trim();
    if (!isValidHttpUrl(trimmed)) {
      setUrlError("Enter a valid http(s) listing URL.");
      return;
    }
    setUrlError("");
    setBusy(true);
    setPhase("processing");
    setResult(null);
    try {
      const res = await landsignalApi.analyzeListingUrl(trimmed, {
        corrections: extra && Object.keys(extra).length ? extra : undefined,
      });
      setResult(res);
      if (res.status === "complete" && res.parcel_id) {
        setPhase("done");
        window.setTimeout(() => {
          router.push(res.report_path || `/parcels/${res.parcel_id}`);
        }, Math.min(1800, 280 * Math.max(1, (res.stages || []).filter((s) => s.status === "done").length)));
      } else if (res.needs_confirmation || res.status === "needs_confirmation") {
        seedCorrections(res);
        setPhase("confirm");
      } else if (res.parcel_id) {
        setPhase("done");
        router.push(res.report_path || `/parcels/${res.parcel_id}`);
      } else if (res.fallback && !res.ok) {
        setPhase("fallback");
      } else {
        seedCorrections(res);
        setPhase("confirm");
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Analyze failed";
      const apiDown =
        /not reachable|not found|404|503|8000|dev:api/i.test(msg) ||
        msg.trim().toLowerCase() === "not found";
      setResult({
        ok: false,
        error: msg,
        fallback: {
          message: apiDown
            ? "Land Signal could not reach the analyze service. Refresh and try again."
            : "We couldn't read enough information from this listing automatically.",
          options: [
            { id: "paste", label: "Paste listing details", href: "/ingest" },
            { id: "manual", label: "Enter address / APN", href: "/ingest" },
          ],
        },
      });
      setPhase("fallback");
    } finally {
      setBusy(false);
    }
  }

  function onSubmit(e?: FormEvent) {
    e?.preventDefault();
    void runAnalyze();
  }

  function onConfirm(e?: FormEvent) {
    e?.preventDefault();
    const payload: Record<string, string> = {};
    for (const [k, v] of Object.entries(corrections)) {
      if (v.trim()) payload[k] = v.trim();
    }
    void runAnalyze(payload);
  }

  const shownStages = doneStages.slice(0, Math.max(1, visibleStageIdx));
  const facts = (result?.facts || []).slice(0, 6);
  const missingKeys = new Set((result?.missing_material || []).map((m) => m.field));
  const showProcess = phase === "processing" || phase === "done" || (phase === "confirm" && !!result);

  const modal =
    open && mounted
      ? createPortal(
          <div
            className="analyze-modal-backdrop"
            role="presentation"
            onClick={(e) => {
              if (e.target === e.currentTarget && !busy) closeModal();
            }}
          >
            <div
              className="analyze-modal"
              role="dialog"
              aria-modal="true"
              aria-labelledby="analyze-modal-title"
            >
              <button
                type="button"
                className="analyze-modal-close"
                aria-label="Close"
                disabled={busy}
                onClick={closeModal}
              >
                ×
              </button>

              <LandLoadingVisual active={phase === "processing" || phase === "done"} />

              <div className="analyze-modal-body">
                <p className="analyze-modal-kicker">Land Signal · URL Intelligence</p>
                <h3 id="analyze-modal-title" className="analyze-modal-title">
                  Analyze Any Land Listing
                </h3>
                <p className="analyze-modal-support">
                  Found land somewhere else? Paste the listing and Land Signal will turn it into a
                  complete intelligence report.
                </p>

                {(phase === "idle" || phase === "confirm" || phase === "fallback") && (
                  <form
                    className="analyze-listing-form"
                    onSubmit={phase === "confirm" ? onConfirm : onSubmit}
                  >
                    {phase !== "confirm" ? (
                      <>
                        <label className="analyze-listing-label">
                          Paste a land listing URL
                          <input
                            className="field analyze-listing-input"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            placeholder="https://..."
                            inputMode="url"
                            autoComplete="url"
                            disabled={busy}
                            autoFocus
                          />
                        </label>
                        {urlError ? <p className="analyze-listing-error">{urlError}</p> : null}
                      </>
                    ) : null}

                    {phase === "confirm" && result ? (
                      <div className="analyze-listing-confirm">
                        <p className="analyze-listing-note">
                          {result.note ||
                            "We screened the listing URL. Confirm anything still blank, then run the report."}
                        </p>
                        <div className="analyze-listing-grid">
                          {(
                            [
                              ["title", "Title"],
                              ["acreage", "Acres"],
                              ["asking_price_usd", "Asking price (USD)"],
                              ["state", "State"],
                              ["county", "County"],
                              ["address", "Address"],
                              ["apn", "APN"],
                              ["coordinates", "Coordinates (lat, lon)"],
                            ] as const
                          ).map(([field, label]) => {
                            const required =
                              missingKeys.has(field) ||
                              (field === "coordinates" && missingKeys.has("coordinates"));
                            const val = corrections[field] || "";
                            if (
                              !required &&
                              !val &&
                              !["title", "acreage", "state", "coordinates"].includes(field)
                            ) {
                              return null;
                            }
                            return (
                              <label key={field} className="analyze-listing-label">
                                {label}
                                {required ? " *" : ""}
                                <input
                                  className={`field analyze-listing-input${required && !val ? " is-missing" : ""}`}
                                  value={val}
                                  onChange={(e) =>
                                    setCorrections((c) => ({ ...c, [field]: e.target.value }))
                                  }
                                  placeholder={
                                    field === "coordinates"
                                      ? "34.05, -118.24"
                                      : field === "acreage"
                                        ? "34.7"
                                        : field === "state"
                                          ? "CA"
                                          : ""
                                  }
                                  disabled={busy}
                                  required={required}
                                />
                              </label>
                            );
                          })}
                        </div>
                        <button
                          type="submit"
                          className="btn btn-primary analyze-listing-cta"
                          disabled={busy}
                        >
                          {busy ? "Analyzing…" : "Analyze Property →"}
                        </button>
                      </div>
                    ) : null}

                    {phase === "fallback" && result?.fallback ? (
                      <div className="analyze-listing-fallback">
                        <p>{result.fallback.message}</p>
                        {result.error ? (
                          <p className="analyze-listing-error">{result.error}</p>
                        ) : null}
                        <div className="analyze-listing-fallback-actions">
                          {(result.fallback.options || []).map((o) => (
                            <Link
                              key={o.id}
                              href={o.href || "/ingest"}
                              className="btn btn-secondary"
                            >
                              {o.label}
                            </Link>
                          ))}
                        </div>
                      </div>
                    ) : null}

                    {phase === "idle" ? (
                      <button
                        type="submit"
                        className="btn btn-primary analyze-listing-cta"
                        disabled={busy}
                      >
                        Analyze Property →
                      </button>
                    ) : null}
                  </form>
                )}

                {showProcess ? (
                  <div className="analyze-listing-process" aria-live="polite">
                    <ul className="analyze-listing-stages">
                      {(phase === "processing" && !result
                        ? [{ id: "reading_listing", label: "Reading listing", status: "running" }]
                        : shownStages
                      ).map((s) => (
                        <li key={s.id} className={`stage stage-${s.status}`}>
                          <span className="stage-mark" aria-hidden>
                            {s.status === "done" ? "✓" : s.status === "error" ? "!" : "·"}
                          </span>
                          <span>{s.label}</span>
                        </li>
                      ))}
                      {phase === "processing" && result && shownStages.length < STAGE_ORDER.length ? (
                        <li className="stage stage-running">
                          <span className="stage-mark stage-pulse" aria-hidden>
                            ◌
                          </span>
                          <span>Working…</span>
                        </li>
                      ) : null}
                    </ul>
                    {facts.length ? (
                      <ul className="analyze-listing-facts">
                        {facts.map((f) => (
                          <li key={f}>{f}</li>
                        ))}
                      </ul>
                    ) : null}
                    {phase === "done" ? (
                      <p className="analyze-listing-note">Opening full intelligence report…</p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            </div>
          </div>,
          document.body,
        )
      : null;

  return (
    <div className="analyze-listing-wrap">
      <button
        type="button"
        className="btn filter-action-analyze-url analyze-listing-trigger"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          setOpen(true);
          setPhase("idle");
        }}
      >
        <span className="analyze-listing-trigger-sheen" aria-hidden />
        <span className="analyze-listing-trigger-label">Analyze a Listing</span>
      </button>
      {modal}
    </div>
  );
}
