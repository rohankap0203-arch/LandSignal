"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";

export type LocationImage = {
  id: string;
  label: string;
  url: string;
  source: string;
};

type Props = {
  open: boolean;
  onClose: () => void;
  title: string;
  location?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  acres?: number | null;
  images?: LocationImage[];
};

/** Esri World Imagery frames — ATTOM key does not supply MLS listing photos. */
export function buildSatelliteGallery(
  lat: number,
  lon: number,
  acres?: number | null,
): LocationImage[] {
  const basePad =
    acres != null && acres > 0
      ? Math.max(0.0025, Math.min(0.04, Math.sqrt(acres) * 0.0011))
      : 0.006;
  const frames: Array<{ id: string; label: string; mult: number }> = [
    { id: "close", label: "Close-in satellite", mult: 0.55 },
    { id: "parcel", label: "Parcel frame", mult: 1 },
    { id: "context", label: "Neighborhood context", mult: 2.2 },
    { id: "region", label: "Regional context", mult: 4.5 },
  ];
  return frames.map((f) => {
    const pad = basePad * f.mult;
    const url =
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export" +
      `?bbox=${lon - pad},${lat - pad},${lon + pad},${lat + pad}` +
      "&bboxSR=4326&imageSR=4326&size=1024,768&format=jpg&f=image";
    return { id: f.id, label: f.label, url, source: "Esri World Imagery" };
  });
}

export function LocationImagesModal({
  open,
  onClose,
  title,
  location,
  latitude,
  longitude,
  acres,
  images,
}: Props) {
  const [idx, setIdx] = useState(0);
  const gallery = useMemo(() => {
    if (images?.length) return images;
    if (
      latitude == null ||
      longitude == null ||
      !Number.isFinite(latitude) ||
      !Number.isFinite(longitude)
    ) {
      return [] as LocationImage[];
    }
    return buildSatelliteGallery(latitude, longitude, acres);
  }, [images, latitude, longitude, acres]);

  useEffect(() => {
    if (!open) return;
    setIdx(0);
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

  if (!open || typeof document === "undefined") return null;

  const current = gallery[idx];

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
          <div>
            <div className="display text-lg font-semibold leading-snug">{title}</div>
            {location ? <div className="mt-0.5 text-sm text-[var(--muted)]">{location}</div> : null}
          </div>
          <button type="button" className="help-q on" aria-label="Close images" onClick={onClose}>
            ×
          </button>
        </div>

        {current ? (
          <div className="loc-images-stage">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={current.url} alt={current.label} className="loc-images-img" />
            <div className="loc-images-caption">
              <span>{current.label}</span>
              <span className="text-[var(--muted)]">
                {idx + 1} / {gallery.length} · {current.source}
              </span>
            </div>
          </div>
        ) : (
          <p className="p-4 text-sm text-[var(--muted)]">
            No coordinates on this file yet — open Intelligence after the parcel is geocoded to view
            satellite frames.
          </p>
        )}

        {gallery.length > 1 ? (
          <div className="loc-images-nav">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={idx <= 0}
              onClick={() => setIdx((i) => Math.max(0, i - 1))}
            >
              Previous
            </button>
            <div className="loc-images-dots" aria-hidden>
              {gallery.map((g, i) => (
                <button
                  key={g.id}
                  type="button"
                  className={`loc-images-dot ${i === idx ? "on" : ""}`}
                  onClick={() => setIdx(i)}
                  aria-label={g.label}
                />
              ))}
            </div>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={idx >= gallery.length - 1}
              onClick={() => setIdx((i) => Math.min(gallery.length - 1, i + 1))}
            >
              Next
            </button>
          </div>
        ) : null}

        <p className="loc-images-note">
          Satellite frames of this location (Esri World Imagery). ATTOM enriches property records under
          the current key — it does not supply MLS listing photo galleries.
        </p>
      </div>
    </div>,
    document.body,
  );
}
