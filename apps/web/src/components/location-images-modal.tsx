"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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

function streetViewEmbedUrl(lat: number, lon: number): string {
  return `https://www.google.com/maps/embed?origin=mfe&pb=!6m6!1m5!2m2!1d${lat}!2d${lon}!4f0!5f1`;
}

function streetViewThumb(lat: number, lon: number, acres?: number | null): string {
  const basePad =
    acres != null && acres > 0
      ? Math.max(0.0025, Math.min(0.04, Math.sqrt(acres) * 0.0011))
      : 0.006;
  const closePad = basePad * 0.55;
  return (
    "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export" +
    `?bbox=${lon - closePad},${lat - closePad},${lon + closePad},${lat + closePad}` +
    "&bboxSR=4326&imageSR=4326&size=320x240&format=jpg&f=image"
  );
}

/** Client fallback — one clear USGS aerial (not identical Esri zoom clones). */
export function buildAerialFallback(
  lat: number,
  lon: number,
  acres?: number | null,
): LocationImage[] {
  const basePad =
    acres != null && acres > 0
      ? Math.max(0.0025, Math.min(0.04, Math.sqrt(acres) * 0.0011))
      : 0.006;
  const frames: Array<{ id: string; label: string; mult: number }> = [
    { id: "usgs-parcel", label: "Aerial — parcel", mult: 0.85 },
    { id: "usgs-area", label: "Aerial — surrounding land", mult: 2.6 },
  ];
  const streetEmbed: LocationImage = {
    id: "google-street-view",
    label: "Street View",
    url: streetViewEmbedUrl(lat, lon),
    thumb_url: streetViewThumb(lat, lon, acres),
    source: "Google Street View",
    kind: "streetview",
    embed: true,
  };
  return [
    streetEmbed,
    ...frames.map((f) => {
      const pad = basePad * f.mult;
      const url =
        "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export" +
        `?bbox=${lon - pad},${lat - pad},${lon + pad},${lat + pad}` +
        "&bboxSR=4326&imageSR=4326&size=1440,1080&format=jpg&f=image";
      return { id: f.id, label: f.label, url, source: "USGS The National Map", kind: "aerial" };
    }),
  ];
}

/** @deprecated use buildAerialFallback */
export const buildSatelliteGallery = buildAerialFallback;

/** One-line explanation of what this frame shows relative to the land. */
function landRelationLine(img: LocationImage): string {
  const kind = img.kind || "";
  const label = (img.label || "").trim();
  const MAX = 88; // fits one wrapped line on phone + desktop without clipping

  const fit = (s: string): string => {
    const clean = s.replace(/\s+/g, " ").trim();
    if (clean.length <= MAX) return clean;
    const cut = clean.slice(0, MAX - 1);
    const at = Math.max(cut.lastIndexOf(" "), cut.lastIndexOf("—"), cut.lastIndexOf("-"));
    const base = (at > MAX * 0.55 ? cut.slice(0, at) : cut).trimEnd().replace(/[.,;:]+$/, "");
    return `${base}…`;
  };

  if (kind === "streetview" || img.embed) {
    return fit("Street-level view of the land from the nearest road — look around the parcel.");
  }
  if (kind === "street") {
    const facing = label.match(/facing\s+([A-Z]{1,2})\b/i)?.[1];
    if (facing) {
      return fit(`Street-level photo near the land, looking ${facing} along the approach.`);
    }
    const dist = label.match(/([\d.]+)\s*(m|km)\b/i);
    if (dist) {
      return fit(`Street-level photo of the approach about ${dist[1]} ${dist[2]} from the land.`);
    }
    return fit("Street-level photo of the road approach near this land.");
  }
  if (kind === "aerial") {
    if (/surround/i.test(label)) {
      return fit("Wider aerial of the land and the ground around it.");
    }
    return fit("Overhead aerial centered on this land.");
  }
  if (kind === "ground") {
    if (/^Nearby\s*[—–-]/i.test(label)) {
      const place = label.replace(/^Nearby\s*[—–-]\s*/i, "").trim();
      return fit(
        place
          ? `Nearby place context for this land — ${place}.`
          : "Nearby place photo for context around this land.",
      );
    }
    const cleaned = label
      .replace(/\.(jpe?g|png|webp|gif)\b.*/i, "")
      .replace(/\s*[·•]\s*\d+\s*m\b.*/i, "")
      .replace(/\s+/g, " ")
      .trim();
    if (cleaned) {
      return fit(`Ground photo near this land — ${cleaned}.`);
    }
    return fit("Ground-level photo from near this land for local context.");
  }
  return fit(label || "View of this land and its surroundings.");
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
  const [loading, setLoading] = useState(false);
  const [fetched, setFetched] = useState<LocationImage[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [svResetKey, setSvResetKey] = useState(0);
  const thumbStripRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setIdx(0);
    setError(null);
    setFetched(null);
    setSvResetKey(0);

    let cancelled = false;
    const run = async () => {
      if (images?.length) {
        setFetched(images);
        return;
      }

      const hasCoords =
        latitude != null &&
        longitude != null &&
        Number.isFinite(latitude) &&
        Number.isFinite(longitude);

      if (!parcelId) {
        if (hasCoords) {
          setFetched(buildAerialFallback(latitude!, longitude!, acres));
        }
        return;
      }

      setLoading(true);
      try {
        const payload = await landsignalApi.locationImages(parcelId);
        if (cancelled) return;
        const next = (payload.images || []).map((img) => ({
          id: img.id,
          label: img.label,
          url: img.url,
          thumb_url: img.thumb_url,
          source: img.attribution || img.source,
          kind: img.kind,
          attribution: img.attribution,
          embed: Boolean((img as { embed?: boolean }).embed) || img.kind === "streetview",
        }));
        if (next.length) {
          setFetched(next);
        } else if (hasCoords) {
          setFetched(buildAerialFallback(latitude!, longitude!, acres));
        }
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Could not load images");
        if (hasCoords) {
          setFetched(buildAerialFallback(latitude!, longitude!, acres));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [open, parcelId, images, latitude, longitude, acres]);

  const gallery = useMemo(() => fetched || [], [fetched]);

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
              {!loading && gallery.length > 0 ? (
                <span className="loc-images-head-count">
                  {idx + 1} / {gallery.length}
                </span>
              ) : null}
            </div>
          </div>
          <button type="button" className="help-q on" aria-label="Close images" onClick={onClose}>
            ×
          </button>
        </div>

        {loading ? (
          <div className="loc-images-loading" role="status" aria-live="polite">
            <div className="images-scout" aria-hidden>
              <div className="images-scout-stage">
                <span className="images-scout-flash" />
                <span className="images-scout-shot s1">
                  <span className="images-scout-frame" />
                </span>
                <span className="images-scout-shot s2">
                  <span className="images-scout-frame" />
                </span>
                <span className="images-scout-shot s3">
                  <span className="images-scout-frame" />
                </span>
              </div>
              <div className="images-scout-copy">
                <div className="display text-xl font-semibold text-[var(--ink)]">Scouting the view…</div>
                <p className="mt-1 text-sm text-[var(--muted)]">Capturing Street View and nearby land shots</p>
                <div className="images-scout-dots">
                  <span />
                  <span />
                  <span />
                </div>
              </div>
            </div>
          </div>
        ) : current ? (
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
                <img src={current.url} alt={current.label} className="loc-images-img" />
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
                      fill="currentColor"
                      d="M12 5V2L8 6l4 4V7c3.31 0 6 2.69 6 6a6 6 0 0 1-9.33 4.98l-1.32 1.48A8 8 0 0 0 20 13c0-4.42-3.58-8-8-8zm-6.93 5.18A7.95 7.95 0 0 0 4 13c0 1.85.63 3.55 1.69 4.9l1.42-1.42A5.96 5.96 0 0 1 6 13c0-.9.2-1.75.55-2.51l-1.48-1.31z"
                    />
                  </svg>
                </button>
              ) : null}
              {/* Covers Google embed footer (keyboard shortcuts / terms / report). */}
              {isEmbed ? <div className="loc-images-embed-mask" aria-hidden /> : null}
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
                      <img src={g.thumb_url || g.url} alt="" loading="lazy" />
                      {g.kind === "streetview" || g.embed ? (
                        <span className="loc-images-thumb-badge" aria-hidden>
                          360°
                        </span>
                      ) : null}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
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
