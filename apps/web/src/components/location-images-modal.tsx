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
  const closePad = basePad * 0.55;
  const streetThumb =
    "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export" +
    `?bbox=${lon - closePad},${lat - closePad},${lon + closePad},${lat + closePad}` +
    "&bboxSR=4326&imageSR=4326&size=320x240&format=jpg&f=image";
  const streetEmbed: LocationImage = {
    id: "google-street-view",
    label: "Street View — look around",
    url: `https://www.google.com/maps/embed?origin=mfe&pb=!6m6!1m5!2m2!1d${lat}!2d${lon}!4f0!5f1`,
    thumb_url: streetThumb,
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
  const thumbStripRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setIdx(0);
    setError(null);
    setFetched(null);

    let cancelled = false;
    const run = async () => {
      if (images?.length) {
        setFetched(images);
        return;
      }
      if (!parcelId) {
        if (
          latitude != null &&
          longitude != null &&
          Number.isFinite(latitude) &&
          Number.isFinite(longitude)
        ) {
          setFetched(buildAerialFallback(latitude, longitude, acres));
        }
        return;
      }
      setLoading(true);
      try {
        const payload = await landsignalApi.locationImages(parcelId);
        if (cancelled) return;
        setFetched(
          (payload.images || []).map((img) => ({
            id: img.id,
            label: img.label,
            url: img.url,
            thumb_url: img.thumb_url,
            source: img.attribution || img.source,
            kind: img.kind,
            attribution: img.attribution,
            embed: Boolean((img as { embed?: boolean }).embed) || img.kind === "streetview",
          })),
        );
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Could not load images");
        if (
          latitude != null &&
          longitude != null &&
          Number.isFinite(latitude) &&
          Number.isFinite(longitude)
        ) {
          setFetched(buildAerialFallback(latitude, longitude, acres));
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
            <div className="loc-images-stage">
              {isEmbed ? (
                <iframe
                  key={current.id}
                  className="loc-images-embed"
                  src={current.url}
                  title={current.label}
                  allow="accelerometer; gyroscope; fullscreen; geolocation"
                  loading="lazy"
                  referrerPolicy="no-referrer-when-downgrade"
                />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={current.url} alt={current.label} className="loc-images-img" />
              )}
              <div className="loc-images-caption">
                <span>{current.label}</span>
              </div>
            </div>

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
