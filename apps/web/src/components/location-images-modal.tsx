"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { landsignalApi } from "@/lib/api";

export type LocationImage = {
  id: string;
  label: string;
  url: string;
  thumb_url?: string;
  source: string;
  kind?: string;
  attribution?: string;
  embed?: boolean;
  caption?: string;
  distance_m?: number | null;
};

type MapsLinks = {
  google_maps?: string;
  google_street_view?: string;
  google_earth?: string;
  openstreetmap?: string;
  kartaview?: string;
};

type Props = {
  open: boolean;
  onClose: () => void;
  title: string;
  location?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  acres?: number | null;
  parcelId?: string | null;
  images?: LocationImage[];
};

type ApiImage = {
  id: string;
  label: string;
  url: string;
  thumb_url?: string;
  source: string;
  kind: string;
  attribution?: string;
  page_url?: string | null;
  embed?: boolean;
  caption?: string;
  distance_m?: number | null;
};

const clientCache = new Map<
  string,
  { at: number; images: LocationImage[]; note?: string; maps?: MapsLinks }
>();
const CLIENT_TTL_MS = 40 * 60 * 1000;
const inflight = new Map<string, Promise<void>>();

function padForAcres(acres?: number | null, mult = 1) {
  const base =
    acres != null && acres > 0
      ? Math.max(0.0028, Math.min(0.045, Math.sqrt(acres) * 0.00115))
      : 0.006;
  return base * mult;
}

function esriExport(lat: number, lon: number, pad: number, size: string) {
  return (
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export" +
    `?bbox=${lon - pad},${lat - pad},${lon + pad},${lat + pad}` +
    `&bboxSR=4326&imageSR=4326&size=${size}&format=jpg&f=image`
  );
}

function usgsExport(lat: number, lon: number, pad: number, size: string) {
  return (
    "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export" +
    `?bbox=${lon - pad},${lat - pad},${lon + pad},${lat + pad}` +
    `&bboxSR=4326&imageSR=4326&size=${size}&format=jpg&f=image`
  );
}

function streetViewEmbedUrl(lat: number, lon: number): string {
  return `https://www.google.com/maps/embed?origin=mfe&pb=!6m6!1m5!2m2!1d${lat}!2d${lon}!4f0!5f1`;
}

/** Instant client gallery — no API wait. Matches Zillow-style "open → see land". */
export function buildAerialFallback(
  lat: number,
  lon: number,
  acres?: number | null,
): LocationImage[] {
  const pad = padForAcres(acres, 0.9);
  const padWide = padForAcres(acres, 2.6);
  const padUsgs = padForAcres(acres, 0.85);
  return [
    {
      id: "esri-parcel",
      label: "Satellite — this land",
      url: esriExport(lat, lon, pad, "1440,1080"),
      thumb_url: esriExport(lat, lon, pad, "480,360"),
      source: "Esri World Imagery",
      kind: "aerial",
      caption: "Clear satellite view centered on this land.",
    },
    {
      id: "usgs-parcel",
      label: "Aerial — USGS of this land",
      url: usgsExport(lat, lon, padUsgs, "1440,1080"),
      thumb_url: usgsExport(lat, lon, padUsgs, "480,360"),
      source: "USGS The National Map",
      kind: "aerial",
      caption: "USGS aerial of the same pin for a second look.",
    },
    {
      id: "esri-area",
      label: "Satellite — surrounding land",
      url: esriExport(lat, lon, padWide, "1440,1080"),
      thumb_url: esriExport(lat, lon, padWide, "480,360"),
      source: "Esri World Imagery",
      kind: "aerial",
      caption: "Wider satellite of the land and neighboring ground.",
    },
    {
      id: "google-street-view",
      label: "Street View — look around",
      url: streetViewEmbedUrl(lat, lon),
      thumb_url: esriExport(lat, lon, padForAcres(acres, 0.55), "320,240"),
      source: "Google Street View",
      kind: "streetview",
      embed: true,
      caption: "Interactive street-level view from the nearest road coverage.",
    },
  ];
}

/** @deprecated use buildAerialFallback */
export const buildSatelliteGallery = buildAerialFallback;

function mapApiImages(rows: ApiImage[]): LocationImage[] {
  return (rows || []).map((img) => ({
    id: img.id,
    label: img.label,
    url: img.url,
    thumb_url: img.thumb_url,
    source: img.attribution || img.source,
    kind: img.kind,
    attribution: img.attribution,
    embed: Boolean(img.embed) || img.kind === "streetview",
    caption: img.caption,
    distance_m: img.distance_m,
  }));
}

/** Prefetch full gallery so View Images opens warm. */
export function prefetchLocationImages(parcelId: string | null | undefined) {
  if (!parcelId) return;
  const cached = clientCache.get(parcelId);
  if (cached && Date.now() - cached.at < CLIENT_TTL_MS) return;
  if (inflight.has(parcelId)) return;
  const p = landsignalApi
    .locationImages(parcelId, { mode: "full" })
    .then((payload) => {
      clientCache.set(parcelId, {
        at: Date.now(),
        images: mapApiImages(payload.images || []),
        note: payload.note,
        maps: payload.maps,
      });
    })
    .catch(() => undefined)
    .finally(() => {
      inflight.delete(parcelId);
    });
  inflight.set(parcelId, p.then(() => undefined));
}

function landRelationLine(img: LocationImage): string {
  if (img.caption) return img.caption;
  const kind = img.kind || "";
  const label = (img.label || "").trim();

  if (kind === "streetview" || img.embed) {
    return "Interactive street-level view from the nearest road coverage.";
  }
  if (kind === "street") {
    const facing = label.match(/facing\s+([A-Z]{1,2})\b/i)?.[1];
    if (facing) return `Drive-by photo on the road near this land, looking ${facing}.`;
    const dist = label.match(/([\d.]+)\s*(m|km)\b/i);
    if (dist) return `Drive-by photo about ${dist[1]} ${dist[2]} from this land.`;
    return "Drive-by photo of the road approach near this land.";
  }
  if (kind === "aerial") {
    if (/surround/i.test(label)) return "Wider satellite of the land and neighboring ground.";
    if (/usgs/i.test(label)) return "USGS aerial of this land.";
    return "Clear satellite view centered on this land.";
  }
  if (kind === "ground") {
    const cleaned = label
      .replace(/\.(jpe?g|png|webp|gif)\b.*/i, "")
      .replace(/\s*[·•]\s*\d+\s*m\b.*/i, "")
      .replace(/\s+/g, " ")
      .trim();
    if (cleaned) return `Ground photo near this land: ${cleaned}.`;
    return "Ground-level photo from near this land.";
  }
  return label || "View of this land and its surroundings.";
}

function kindBadge(img: LocationImage): string {
  const k = img.kind || "";
  if (k === "streetview" || img.embed) return "360°";
  if (k === "street") return "Road";
  if (k === "aerial") return "Sat";
  if (k === "ground") return "Ground";
  return "View";
}

/** Detect near-black / near-white / flat blank tiles (common bad aerial exports). */
function isBlankOrBlackFrame(imgEl: HTMLImageElement): boolean {
  try {
    const w = Math.min(48, imgEl.naturalWidth || 0);
    const h = Math.min(36, imgEl.naturalHeight || 0);
    if (w < 8 || h < 8) return true;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) return false;
    ctx.drawImage(imgEl, 0, 0, w, h);
    const data = ctx.getImageData(0, 0, w, h).data;
    let dark = 0;
    let light = 0;
    let sum = 0;
    let sumSq = 0;
    let n = 0;
    for (let i = 0; i < data.length; i += 16) {
      const r = data[i];
      const g = data[i + 1];
      const b = data[i + 2];
      const a = data[i + 3];
      if (a < 8) {
        dark++;
        n++;
        continue;
      }
      const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      sum += lum;
      sumSq += lum * lum;
      n++;
      if (lum < 16) dark++;
      if (lum > 246) light++;
    }
    if (!n) return true;
    const mean = sum / n;
    const variance = sumSq / n - mean * mean;
    if (dark / n > 0.9) return true;
    if (light / n > 0.92) return true;
    // Flat almost-uniform tile (failed export / solid color)
    if (variance < 18 && (mean < 28 || mean > 235)) return true;
    return false;
  } catch {
    return false;
  }
}

export function LocationImagesModal({
  open,
  onClose,
  title,
  location,
  latitude,
  longitude,
  acres,
  parcelId,
  images,
}: Props) {
  const [idx, setIdx] = useState(0);
  const [enriching, setEnriching] = useState(false);
  const [fetched, setFetched] = useState<LocationImage[] | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [maps, setMaps] = useState<MapsLinks | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [svResetKey, setSvResetKey] = useState(0);
  const [rejected, setRejected] = useState<Set<string>>(() => new Set());
  const thumbStripRef = useRef<HTMLDivElement | null>(null);
  const hasCoords =
    latitude != null &&
    longitude != null &&
    Number.isFinite(latitude) &&
    Number.isFinite(longitude);

  const applyGallery = useCallback((next: LocationImage[], meta?: { note?: string; maps?: MapsLinks }) => {
    setFetched(next);
    if (meta?.note) setNote(meta.note);
    if (meta?.maps) setMaps(meta.maps);
  }, []);

  useEffect(() => {
    if (!open) return;
    setIdx(0);
    setError(null);
    setSvResetKey(0);
    setRejected(new Set());
    setNote(null);
    setMaps(null);

    // 1) Instant paint — never make the user stare at a scout spinner for aerials.
    if (images?.length) {
      applyGallery(images);
      setEnriching(false);
      return;
    }
    if (hasCoords) {
      applyGallery(buildAerialFallback(latitude!, longitude!, acres), {
        note: "Satellite of this land loads instantly. Nearby road photos fill in next.",
      });
    } else {
      setFetched(null);
    }

    if (!parcelId) {
      setEnriching(false);
      return;
    }

    let cancelled = false;
    const warm = clientCache.get(parcelId);
    if (warm && Date.now() - warm.at < CLIENT_TTL_MS && warm.images.length) {
      applyGallery(warm.images, { note: warm.note, maps: warm.maps });
      setEnriching(false);
      return () => {
        cancelled = true;
      };
    }

    setEnriching(true);
    const run = async () => {
      try {
        const payload = await landsignalApi.locationImages(parcelId, { mode: "full" });
        if (cancelled) return;
        const next = mapApiImages(payload.images || []);
        if (next.length) {
          clientCache.set(parcelId, {
            at: Date.now(),
            images: next,
            note: payload.note,
            maps: payload.maps,
          });
          applyGallery(next, { note: payload.note, maps: payload.maps });
        } else if (hasCoords) {
          applyGallery(buildAerialFallback(latitude!, longitude!, acres));
        }
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Could not load nearby photos");
        // Keep instant aerials — never blank the modal on enrich failure.
      } finally {
        if (!cancelled) setEnriching(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [open, parcelId, images, latitude, longitude, acres, hasCoords, applyGallery]);

  const gallery = useMemo(
    () => (fetched || []).filter((g) => !rejected.has(g.id)),
    [fetched, rejected],
  );

  useEffect(() => {
    if (idx >= gallery.length && gallery.length > 0) {
      setIdx(gallery.length - 1);
    }
  }, [gallery.length, idx]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") setIdx((i) => Math.min(gallery.length - 1, i + 1));
      if (e.key === "ArrowLeft") setIdx((i) => Math.max(0, i - 1));
    };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose, gallery.length]);

  useEffect(() => {
    const strip = thumbStripRef.current;
    if (!strip) return;
    const active = strip.querySelector<HTMLElement>(".loc-images-thumb.on");
    active?.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" });
  }, [idx, gallery.length]);

  const rejectFrame = useCallback((id: string) => {
    setRejected((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  }, []);

  if (!open || typeof document === "undefined") return null;

  const current = gallery[idx];
  const isEmbed = Boolean(current?.embed || current?.kind === "streetview");
  const showReset = isEmbed;

  const resetStreetView = () => {
    setSvResetKey((k) => k + 1);
  };

  return createPortal(
    <div className="help-modal-backdrop loc-images-backdrop" role="presentation" onClick={onClose}>
      <div
        className="loc-images-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Location images — ${title}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="loc-images-head">
          <div className="loc-images-head-main">
            <div className="display text-lg font-semibold leading-snug">{title}</div>
            <div className="loc-images-head-meta">
              {location ? <span className="loc-images-head-location">{location}</span> : null}
              {gallery.length > 0 ? (
                <span className="loc-images-head-count">
                  {idx + 1} / {gallery.length}
                </span>
              ) : null}
              {enriching ? (
                <span className="loc-images-head-enriching" aria-live="polite">
                  Finding nearby roads…
                </span>
              ) : null}
            </div>
          </div>
          <button type="button" className="help-q on" aria-label="Close images" onClick={onClose}>
            ×
          </button>
        </div>

        {current ? (
          <>
            <div className={`loc-images-stage ${isEmbed ? "is-embed" : ""}`}>
              {isEmbed ? (
                <iframe
                  key={`${current.id}-${svResetKey}`}
                  className="loc-images-embed"
                  src={current.url}
                  title={current.label || "Street View"}
                  allow="accelerometer; gyroscope; fullscreen; geolocation"
                  loading="eager"
                  referrerPolicy="no-referrer-when-downgrade"
                />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={current.id}
                  src={current.url}
                  alt={current.label}
                  className="loc-images-img"
                  onLoad={(e) => {
                    const el = e.currentTarget;
                    if (isBlankOrBlackFrame(el)) {
                      rejectFrame(current.id);
                    }
                  }}
                  onError={() => rejectFrame(current.id)}
                />
              )}
              {showReset ? (
                <button
                  type="button"
                  className="loc-images-reset"
                  title="Reset Street View to start"
                  aria-label="Reset Street View to starting point"
                  onClick={resetStreetView}
                >
                  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
                    <path
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.1"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9.5 6.5 6 10l3.5 3.5M6 10h7.25a5.25 5.25 0 1 1 0 10.5H11"
                    />
                  </svg>
                </button>
              ) : null}
              {isEmbed ? <div className="loc-images-embed-mask" aria-hidden /> : null}
              <span className="loc-images-kind-chip" aria-hidden>
                {kindBadge(current)}
              </span>
            </div>

            <p className="loc-images-relation" title={landRelationLine(current)}>
              {landRelationLine(current)}
            </p>

            {gallery.length > 1 ? (
              <div className="loc-images-controls">
                <div className="loc-images-arrows">
                  <button
                    type="button"
                    className="loc-images-arrow"
                    disabled={idx <= 0}
                    aria-label="Previous image"
                    onClick={() => setIdx((i) => Math.max(0, i - 1))}
                  >
                    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
                      <path
                        fill="currentColor"
                        d="M15.41 7.41 14 6l-6 6 6 6 1.41-1.41L10.83 12z"
                      />
                    </svg>
                  </button>
                  <button
                    type="button"
                    className="loc-images-arrow"
                    disabled={idx >= gallery.length - 1}
                    aria-label="Next image"
                    onClick={() => setIdx((i) => Math.min(gallery.length - 1, i + 1))}
                  >
                    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
                      <path
                        fill="currentColor"
                        d="M10 6 8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"
                      />
                    </svg>
                  </button>
                </div>

                <div
                  className="loc-images-thumbs"
                  ref={thumbStripRef}
                  role="listbox"
                  aria-label="Image thumbnails"
                >
                  {gallery.map((g, i) => (
                    <button
                      key={g.id}
                      type="button"
                      role="option"
                      aria-selected={i === idx}
                      aria-label={g.label}
                      className={`loc-images-thumb ${i === idx ? "on" : ""} ${
                        g.kind === "streetview" || g.embed ? "is-street" : ""
                      }`}
                      onClick={() => setIdx(i)}
                    >
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={g.thumb_url || g.url}
                        alt=""
                        loading="lazy"
                        onLoad={(e) => {
                          if (g.embed || g.kind === "streetview") return;
                          if (isBlankOrBlackFrame(e.currentTarget)) {
                            rejectFrame(g.id);
                          }
                        }}
                        onError={() => {
                          if (g.embed || g.kind === "streetview") return;
                          rejectFrame(g.id);
                        }}
                      />
                      <span className="loc-images-thumb-badge" aria-hidden>
                        {kindBadge(g)}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}

            {note ? <p className="loc-images-note">{note}</p> : null}
            {maps && (maps.google_maps || maps.google_street_view || maps.kartaview) ? (
              <div className="loc-images-links">
                {maps.google_maps ? (
                  <a href={maps.google_maps} target="_blank" rel="noreferrer">
                    Google Maps
                  </a>
                ) : null}
                {maps.google_street_view ? (
                  <a href={maps.google_street_view} target="_blank" rel="noreferrer">
                    Open Street View
                  </a>
                ) : null}
                {maps.kartaview ? (
                  <a href={maps.kartaview} target="_blank" rel="noreferrer">
                    KartaView map
                  </a>
                ) : null}
              </div>
            ) : null}
            {error ? <p className="loc-images-note loc-images-note--warn">{error}</p> : null}
          </>
        ) : (
          <p className="p-4 text-sm text-[var(--muted)]">
            {error ||
              "No coordinates on this file yet — open Intelligence after the parcel is geocoded to view imagery."}
          </p>
        )}
      </div>
    </div>,
    document.body,
  );
}
