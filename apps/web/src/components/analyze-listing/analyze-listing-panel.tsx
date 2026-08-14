"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";
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

export function AnalyzeListingPanel() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [urlError, setUrlError] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<UrlAnalyzeResult | null>(null);
  const [visibleStageIdx, setVisibleStageIdx] = useState(0);
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const stages = result?.stages || [];
  const doneStages = useMemo(
    () => stages.filter((s) => s.status === "done" || s.status === "error"),
    [stages],
  );

  // Replay completed stages progressively for a premium feel (real stage list from API)
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
    }, 280);
    return () => window.clearInterval(id);
  }, [phase, doneStages.length, result?.parcel_id]);

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
        // Brief beat so stages finish animating, then open report
        window.setTimeout(() => {
          router.push(res.report_path || `/parcels/${res.parcel_id}`);
        }, Math.min(2200, 320 * Math.max(1, (res.stages || []).filter((s) => s.status === "done").length)));
      } else if (res.fallback && (res.missing_material?.length ?? 0) >= 2 && !res.ok) {
        setPhase("fallback");
      } else if (res.needs_confirmation || res.status === "needs_confirmation") {
        setPhase("confirm");
        const seed: Record<string, string> = {};
        for (const m of res.missing_material || []) {
          if (m.field === "coordinates") seed.coordinates = "";
          else seed[m.field] = "";
        }
        setCorrections((c) => ({ ...seed, ...c }));
      } else if (res.parcel_id) {
        setPhase("done");
        router.push(res.report_path || `/parcels/${res.parcel_id}`);
      } else {
        setPhase("fallback");
      }
    } catch (e) {
      setResult({
        ok: false,
        error: e instanceof Error ? e.message : "Analyze failed",
        fallback: {
          message: "We couldn't read enough information from this listing automatically.",
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
  const facts = (result?.facts || []).slice(0, 5);

  return (
    <div className="analyze-listing-wrap">
      <button
        type="button"
        className={`btn btn-secondary filter-action-analyze-url${open ? " is-open" : ""}`}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        Analyze a Listing
      </button>

      {open ? (
        <div className="analyze-listing-panel" role="region" aria-label="Analyze any land listing">
          <h3 className="analyze-listing-title">Analyze Any Land Listing</h3>
          <p className="analyze-listing-support">
            Found land somewhere else? Paste the listing and Land Signal will turn it into a complete
            intelligence report.
          </p>

          {phase === "idle" || phase === "confirm" || phase === "fallback" ? (
            <form className="analyze-listing-form" onSubmit={phase === "confirm" ? onConfirm : onSubmit}>
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
                    />
                  </label>
                  {urlError ? <p className="analyze-listing-error">{urlError}</p> : null}
                </>
              ) : null}

              {phase === "confirm" && result ? (
                <div className="analyze-listing-confirm">
                  <p className="analyze-listing-note">
                    {result.note || "A few critical fields need confirmation before analysis."}
                  </p>
                  {(result.missing_material || []).map((m) => (
                    <label key={m.field} className="analyze-listing-label">
                      {m.prompt}
                      <input
                        className="field analyze-listing-input"
                        value={corrections[m.field] || ""}
                        onChange={(e) =>
                          setCorrections((c) => ({ ...c, [m.field]: e.target.value }))
                        }
                        placeholder={
                          m.field === "coordinates"
                            ? "34.05, -118.24"
                            : m.field === "acreage"
                              ? "34.7"
                              : m.unit || m.field
                        }
                        disabled={busy}
                      />
                    </label>
                  ))}
                  <button type="submit" className="btn btn-primary analyze-listing-cta" disabled={busy}>
                    {busy ? "Analyzing…" : "Analyze Property →"}
                  </button>
                </div>
              ) : null}

              {phase === "fallback" && result?.fallback ? (
                <div className="analyze-listing-fallback">
                  <p>{result.fallback.message}</p>
                  <div className="analyze-listing-fallback-actions">
                    {(result.fallback.options || []).map((o) => (
                      <Link key={o.id} href={o.href || "/ingest"} className="btn btn-secondary">
                        {o.label}
                      </Link>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => {
                      setPhase("idle");
                      setResult(null);
                    }}
                  >
                    Try another URL
                  </button>
                </div>
              ) : null}

              {phase === "idle" ? (
                <button type="submit" className="btn btn-primary analyze-listing-cta" disabled={busy}>
                  Analyze Property →
                </button>
              ) : null}
            </form>
          ) : null}

          {(phase === "processing" || phase === "done" || phase === "confirm") && result ? (
            <div className="analyze-listing-process" aria-live="polite">
              <ul className="analyze-listing-stages">
                {shownStages.map((s) => (
                  <li key={s.id} className={`stage stage-${s.status}`}>
                    <span className="stage-mark" aria-hidden>
                      {s.status === "done" ? "✓" : s.status === "error" ? "!" : "·"}
                    </span>
                    <span>{s.label}</span>
                  </li>
                ))}
                {phase === "processing" && shownStages.length < STAGE_ORDER.length ? (
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
              {result?.duplicate?.message ? (
                <p className="analyze-listing-note">{result.duplicate.message}</p>
              ) : null}
              {phase === "done" ? (
                <p className="analyze-listing-note">Opening full intelligence report…</p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
