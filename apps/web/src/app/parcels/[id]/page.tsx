"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { KnowledgeStateBadge, ProvenanceHint } from "@/components/knowledge-state";
import { ScoreStrip } from "@/components/score-strip";
import { SignalBadge } from "@/components/signal-badge";
import { landsignalApi, money, num, pct } from "@/lib/api";

type AnyRec = Record<string, unknown>;

export default function ParcelIntelligencePage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<AnyRec | null>(null);
  const [memo, setMemo] = useState<string | null>(null);
  const [verdict, setVerdict] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    landsignalApi
      .parcel(params.id)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [params.id]);

  if (error) {
    return <div className="panel p-4 text-[var(--danger)]">{error}</div>;
  }
  if (!data) {
    return <div className="text-[var(--muted)]">Loading intelligence…</div>;
  }

  const parcel = data.parcel as AnyRec;
  const listing = data.listing as AnyRec | null;
  const score = data.score as AnyRec | null;
  const enrichment = data.enrichment as AnyRec | null;
  const dd = (data.due_diligence as AnyRec[]) || [];
  const mapboxStatus = data.mapbox_status as string;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">
              {(listing?.title as string) || (parcel.apn as string) || "Parcel"}
            </h1>
            {score && <SignalBadge signal={score.signal as string} />}
            {parcel.is_demo ? <span className="ks">DEMO</span> : null}
          </div>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {parcel.county as string}, {parcel.state as string} · APN {String(parcel.apn || "—")} ·{" "}
            {num(parcel.acreage as number, 2)} acres
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className="panel px-3 py-2 text-sm"
            onClick={() => landsignalApi.analyze(params.id).then(() => landsignalApi.parcel(params.id).then(setData))}
          >
            Re-run analysis
          </button>
          <button
            type="button"
            className="panel px-3 py-2 text-sm text-[var(--accent)]"
            onClick={() =>
              landsignalApi.memo(params.id).then((m) => {
                setMemo(m.markdown);
                setVerdict(m.verdict);
              })
            }
          >
            Generate investment memo
          </button>
        </div>
      </div>

      <ScoreStrip
        opportunity={score?.opportunity as number}
        risk={score?.risk as number}
        confidence={score?.confidence as number}
        asymmetry={score?.asymmetry as number}
        dealReadiness={score?.deal_readiness as number}
      />

      <div className="grid gap-3 md:grid-cols-3">
        <Fact label="Best strategy" value={String(score?.best_strategy || "—")} />
        <Fact label="Current ask" value={money(listing?.asking_price_usd as number)} />
        <Fact
          label="Model value / mispricing"
          value={`${money(score?.estimated_value_usd as number)} · ${pct(score?.asking_discount_pct as number)}`}
        />
      </div>

      <section className="grid gap-3 lg:grid-cols-2">
        <Narrative title="Why this is interesting" items={score?.why_interesting as string[]} />
        <Narrative title="Why it may be mispriced" items={score?.why_mispriced as string[]} />
        <Narrative title="What could kill the deal" items={score?.what_could_kill as string[]} />
        <Narrative title="Why it may still be available" items={score?.why_still_available as string[]} />
      </section>

      <section className="panel p-4">
        <h2 className="text-sm uppercase tracking-wide text-[var(--muted)]">What needs manual verification</h2>
        <ul className="mt-2 space-y-1 text-sm">
          {((score?.manual_verification as string[]) || []).map((x) => (
            <li key={x}>[ ] {x}</li>
          ))}
        </ul>
      </section>

      <section className="panel p-4">
        <h2 className="text-sm uppercase tracking-wide text-[var(--muted)]">Map</h2>
        {mapboxStatus === "NOT_CONFIGURED" ? (
          <p className="mt-2 text-sm text-[var(--muted)]">
            Mapbox: <strong>NOT_CONFIGURED</strong>. Set <span className="mono">NEXT_PUBLIC_MAPBOX_TOKEN</span>{" "}
            / <span className="mono">MAPBOX_TOKEN</span> for interactive overlays. Centroid:{" "}
            <span className="mono">
              {String(parcel.latitude)}, {String(parcel.longitude)}
            </span>
          </p>
        ) : (
          <p className="mt-2 text-sm">Mapbox token detected — wire Mapbox GL overlays in Phase 1.5.</p>
        )}
      </section>

      <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <EnrichCard title="Soils" prov={enrichment?.soil as AnyRec} />
        <EnrichCard title="Flood" prov={enrichment?.flood as AnyRec} />
        <EnrichCard title="Wetlands" prov={enrichment?.wetlands as AnyRec} />
        <EnrichCard title="Terrain" prov={enrichment?.terrain as AnyRec} />
      </section>

      <section className="panel p-4">
        <h2 className="text-sm uppercase tracking-wide text-[var(--muted)]">Score components</h2>
        <div className="mt-3 table-wrap">
          <table className="radar">
            <thead>
              <tr>
                <th>Category</th>
                <th>Value</th>
                <th>Weight</th>
                <th>Contribution</th>
                <th>State</th>
                <th>Evidence</th>
              </tr>
            </thead>
            <tbody>
              {((score?.components as AnyRec[]) || []).map((c) => (
                <tr key={String(c.category)}>
                  <td>{String(c.category)}</td>
                  <td className="mono">{num(c.value as number, 1)}</td>
                  <td className="mono">{num((c.weight as number) * 100, 0)}%</td>
                  <td className="mono">{num(c.contribution as number, 2)}</td>
                  <td>
                    <KnowledgeStateBadge state={c.knowledge_state as string} />
                  </td>
                  <td className="max-w-[360px] whitespace-normal text-[var(--muted)]">
                    {((c.evidence as string[]) || []).join(" · ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mono mt-3 text-[11px] text-[var(--muted)]">
          {String(score?.algorithm_version)} / {String(score?.weight_version)} / {String(score?.input_hash)}
        </p>
      </section>

      <section className="panel p-4">
        <h2 className="text-sm uppercase tracking-wide text-[var(--muted)]">
          Manual due diligence checklist
        </h2>
        <ul className="mt-2 columns-1 gap-2 text-sm md:columns-2">
          {dd.map((item) => (
            <li key={String(item.label)} className="mb-1">
              [{item.completed ? "x" : " "}] {String(item.label)}
            </li>
          ))}
        </ul>
      </section>

      {memo && (
        <section className="panel p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm uppercase tracking-wide text-[var(--muted)]">Deal memo</h2>
            <span className="badge exceptional">{verdict}</span>
          </div>
          <pre className="mt-3 overflow-auto whitespace-pre-wrap text-sm text-[var(--text)]">{memo}</pre>
        </section>
      )}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel p-3">
      <div className="text-[11px] uppercase tracking-wide text-[var(--muted)]">{label}</div>
      <div className="mt-1 text-lg">{value}</div>
    </div>
  );
}

function Narrative({ title, items }: { title: string; items?: string[] }) {
  return (
    <div className="panel p-4">
      <h2 className="text-sm uppercase tracking-wide text-[var(--muted)]">{title}</h2>
      <ul className="mt-2 space-y-1 text-sm">
        {(items && items.length ? items : ["—"]).map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ul>
    </div>
  );
}

function EnrichCard({ title, prov }: { title: string; prov?: AnyRec }) {
  if (!prov) {
    return (
      <div className="panel p-3">
        <h3 className="text-sm">{title}</h3>
        <p className="mt-2 text-xs text-[var(--muted)]">No enrichment</p>
      </div>
    );
  }
  return (
    <div className="panel p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm">{title}</h3>
        <KnowledgeStateBadge state={prov.knowledge_state as string} />
      </div>
      <pre className="mono mt-2 max-h-40 overflow-auto text-[11px] text-[var(--muted)]">
        {JSON.stringify(prov.normalized || prov.value || {}, null, 2)}
      </pre>
      <div className="mt-2">
        <ProvenanceHint
          source={prov.source as string}
          retrievedAt={prov.retrieved_at as string}
          confidence={prov.confidence as number}
        />
      </div>
    </div>
  );
}
