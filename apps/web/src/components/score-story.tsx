"use client";

import { useEffect, useMemo, useState } from "react";

type AnyRec = Record<string, unknown>;

function firstSentence(text: unknown, max = 120): string {
  const s = String(text || "").trim();
  if (!s) return "";
  const first = s.split(/(?<=[.!?])\s+/)[0] || s;
  if (first.length <= max) return first;
  const cut = first.slice(0, max);
  const at = Math.max(cut.lastIndexOf(" "), cut.lastIndexOf("·"), cut.lastIndexOf("—"));
  const base = (at > max * 0.55 ? cut.slice(0, at) : cut).trimEnd().replace(/[.,;:]+$/, "");
  return `${base}…`;
}

function toneVerb(score: number): string {
  if (score >= 80) return "Strong pull";
  if (score >= 65) return "Helping";
  if (score >= 50) return "Neutral";
  if (score >= 35) return "Dragging";
  return "Holding back";
}

function knowledgeChip(raw: unknown): string | null {
  const s = String(raw || "")
    .replace(/KnowledgeState\./gi, "")
    .toUpperCase();
  if (!s) return null;
  if (s === "KNOWN" || s === "OBSERVED") return "Confirmed";
  if (s === "ESTIMATED" || s === "BLENDED") return "Estimate";
  if (s === "PARTIAL") return "Partial";
  if (s === "UNKNOWN" || s === "TEMPORARILY_UNAVAILABLE") return "Still open";
  return s.replace(/_/g, " ").toLowerCase().replace(/^\w/, (c) => c.toUpperCase());
}

function splitHeadline(headline: string): { lead: string; meta: string | null } {
  const parts = headline.split(/\s·\s/);
  if (parts.length >= 2) {
    return { lead: parts[0].trim(), meta: parts.slice(1).join(" · ").trim() || null };
  }
  return { lead: headline, meta: null };
}

/** Scout edge / Still on the board — expandable field notes. */
export function ScoutInsightPanel({
  tone,
  eyebrow,
  title,
  blurb,
  items,
}: {
  tone: "edge" | "board";
  eyebrow: string;
  title: string;
  blurb: string;
  items: AnyRec[];
}) {
  const [open, setOpen] = useState<number>(0);
  const rows = useMemo(
    () =>
      (items || []).filter((item) => Boolean(String(item?.headline || item || "").trim())),
    [items],
  );

  useEffect(() => {
    setOpen(rows.length ? 0 : -1);
  }, [rows.length]);

  const beatLabel = tone === "edge" ? "Edge" : "Friction";

  return (
    <div className={`panel scout-story scout-story--${tone}`}>
      <div className="scout-story-inner">
        <div className="scout-story-head">
          <div className="scout-story-eyebrow">{eyebrow}</div>
          <h2 className="display scout-story-title">{title}</h2>
          <p className="scout-story-blurb">{blurb}</p>
        </div>

        <div className="scout-story-list" role="list">
          {rows.map((item, i) => {
            const active = open === i;
            const headline = String(item.headline || item).trim();
            const detail = String(item.detail || "").trim();
            const { lead, meta } = splitHeadline(headline);
            return (
              <button
                key={`${headline}-${i}`}
                type="button"
                role="listitem"
                className={`scout-beat${active ? " is-open" : ""}`}
                style={{ animationDelay: `${Math.min(i, 6) * 55}ms` }}
                onClick={() => setOpen(active ? -1 : i)}
                aria-expanded={active}
              >
                <span className="scout-beat-index" aria-hidden>
                  <span className="scout-beat-index-k">{beatLabel}</span>
                  <span className="scout-beat-index-n">{i + 1}</span>
                </span>
                <span className="scout-beat-body">
                  <span className="scout-beat-head">
                    <span className="scout-beat-lead">{lead}</span>
                    <span className="scout-beat-toggle" aria-hidden>
                      {active ? "−" : "+"}
                    </span>
                  </span>
                  {meta ? <span className="scout-beat-meta">{meta}</span> : null}
                  {!active && detail ? (
                    <span className="scout-beat-tease">{firstSentence(detail, 96)}</span>
                  ) : null}
                  <span className={`scout-beat-detail${active && detail ? " is-shown" : ""}`}>
                    {active && detail ? detail : null}
                  </span>
                </span>
              </button>
            );
          })}
          {!rows.length ? (
            <p className="scout-story-empty">No parcel-specific notes on this file yet.</p>
          ) : null}
        </div>
      </div>
    </div>
  );
}

/** Interactive “recipe” for what builds the opportunity score. */
export function OpportunityRecipe({
  identity,
  opportunity,
  ratings,
}: {
  identity: string;
  opportunity: number;
  ratings: AnyRec[];
}) {
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [animated, setAnimated] = useState(false);

  const rows = useMemo(() => {
    return [...(ratings || [])]
      .map((r) => {
        const score = Number(r.score || 0);
        const weight = Number(r.weight_pct || 0);
        const contribution =
          r.contribution != null
            ? Number(r.contribution)
            : (score * weight) / 100;
        return { ...(r as AnyRec), score, weight, contribution } as AnyRec & {
          score: number;
          weight: number;
          contribution: number;
        };
      })
      .sort((a, b) => b.contribution - a.contribution || b.score - a.score);
  }, [ratings]);

  useEffect(() => {
    const t = window.setTimeout(() => setAnimated(true), 40);
    return () => window.clearTimeout(t);
  }, [rows.length]);

  useEffect(() => {
    if (rows.length && openKey == null) {
      setOpenKey(String(rows[0].key));
    }
  }, [rows, openKey]);

  const known = rows.filter((r) => {
    const ks = String(r.knowledge_state || "").toUpperCase();
    return ks === "KNOWN" || ks === "OBSERVED" || ks === "ESTIMATED" || ks === "BLENDED";
  }).length;
  const helpers = rows.filter((r) => r.score >= 65).length;
  const drags = rows.filter((r) => r.score < 50).length;

  return (
    <section id="sec-score" className="panel opportunity-recipe scroll-mt-20">
      <div className="opportunity-recipe-inner">
        <div className="opportunity-recipe-head">
          <div className="opportunity-recipe-eyebrow">Score recipe</div>
          <div className="opportunity-recipe-title-row">
            <div className="min-w-0">
              <h2 className="display opportunity-recipe-title">What makes up the opportunity score</h2>
              <p className="opportunity-recipe-sub">
                {identity ? `${identity} · ` : ""}
                Tap any ingredient — full math stays, just easier to taste.
              </p>
            </div>
            <div className="opportunity-recipe-total" title="Overall opportunity score">
              <span className="opportunity-recipe-total-n">{Math.round(opportunity)}</span>
              <span className="opportunity-recipe-total-d">/100</span>
            </div>
          </div>

          <div className="opportunity-recipe-chips" aria-label="Score snapshot">
            <span className="opportunity-recipe-chip">
              <strong>{known}</strong> of {rows.length} confirmed or estimated
            </span>
            {helpers ? (
              <span className="opportunity-recipe-chip is-up">
                <strong>{helpers}</strong> lifting
              </span>
            ) : null}
            {drags ? (
              <span className="opportunity-recipe-chip is-down">
                <strong>{drags}</strong> dragging
              </span>
            ) : null}
          </div>
        </div>

        <div className="opportunity-recipe-list">
          {rows.map((r, i) => {
            const key = String(r.key);
            const open = openKey === key;
            const scoreN = Number(r.score || 0);
            const weight = Number(r.weight || 0);
            const ks = knowledgeChip(r.knowledge_state);
            const why = String(r.why_this_number || r.plain_english || r.simple || "");
            const drivers = ((r.drivers as string[]) || (r.evidence as string[]) || []).slice(0, 4);
            const verb = toneVerb(scoreN);
            return (
              <button
                key={key}
                type="button"
                className={`recipe-ingredient${open ? " is-open" : ""}`}
                style={{ animationDelay: `${Math.min(i, 8) * 45}ms` }}
                onClick={() => setOpenKey(open ? null : key)}
                aria-expanded={open}
              >
                <div className="recipe-ingredient-top">
                  <span className="recipe-rank" aria-hidden>
                    {i + 1}
                  </span>
                  <div className="recipe-ingredient-main">
                    <div className="recipe-ingredient-title-row">
                      <span className="recipe-ingredient-label">{String(r.label)}</span>
                      <span className={`recipe-verb recipe-verb--${verb.replace(/\s+/g, "-").toLowerCase()}`}>
                        {verb}
                      </span>
                    </div>
                    <div className="recipe-track" aria-hidden>
                      <div
                        className="recipe-track-fill"
                        style={{
                          width: animated ? `${Math.max(3, Math.min(100, scoreN))}%` : "0%",
                          transitionDelay: `${Math.min(i, 8) * 40}ms`,
                        }}
                      />
                    </div>
                    <div className="recipe-meta-row">
                      <span className="recipe-score">
                        {String(r.score_display || `${scoreN.toFixed(0)}/100`)}
                      </span>
                      {weight > 0 ? (
                        <span className="recipe-weight">{weight}% of score</span>
                      ) : null}
                      {ks ? <span className="recipe-ks">{ks}</span> : null}
                    </div>
                  </div>
                  <span className="recipe-toggle" aria-hidden>
                    {open ? "−" : "+"}
                  </span>
                </div>

                <p className="recipe-tease">{open ? why : firstSentence(why, 118)}</p>

                {open ? (
                  <div className="recipe-depth">
                    {String(r.weight_display || "").trim() ? (
                      <p className="recipe-weight-note">{String(r.weight_display)}</p>
                    ) : null}
                    {drivers.length ? (
                      <ul className="recipe-drivers">
                        {drivers.map((d) => (
                          <li key={d}>{d}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}
              </button>
            );
          })}
          {!rows.length ? (
            <p className="scout-story-empty">Score parts will show once this file is analyzed.</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
