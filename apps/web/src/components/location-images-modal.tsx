"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { landsignalApi } from "@/lib/api";

export type LocationImage = {
  id: string;
  label: string;
  url: string;
  source: string;
  kind?: string;
  attribution?: string;
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

/** Client fallback — USGS aerial frames (not identical Esri zoom clones). */
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
    { id: "usgs-close", label: "USGS aerial — close-in", mult: 0.55 },
    { id: "usgs-parcel", label: "USGS aerial — parcel frame", mult: 1 },
    { id: "usgs-area", label: "USGS aerial — surrounding land", mult: 2.4 },
  ];
  return frames.map((f) => {
    const pad = basePad * f.mult;
    const url =
      "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export" +
      `?bbox=${lon - pad},${lat - pad},${lon + pad},${lat + pad}` +
      "&bboxSR=4326&imageSR=4326&size=1280,960&format=jpg&f=image";
    return { id: f.id, label: f.label, url, source: "USGS The National Map", kind: "aerial" };
  });
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
  const [note, setNote] = useState<string>("");
  const [maps, setMaps] = useState<{
    google_maps?: string;
    google_street_view?: string;
    google_earth?: string;
    openstreetmap?: string;
  } | null>(null);
  const [fetched, setFetched] = useState<LocationImage[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setIdx(0);
    setError(null);
    setFetched(null);
    setMaps(null);
    setNote("");

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
          setNote("Showing USGS aerial frames for these coordinates.");
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
            source: img.attribution || img.source,
            kind: img.kind,
            attribution: img.attribution,
          })),
        );
        setMaps(payload.maps || null);
        setNote(payload.note || "");
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
  const groundCount = useMemo(
    () => gallery.filter((g) => g.kind === "ground").length,
    [gallery],
  );

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
            {groundCount > 0 ? (
              <div className="mt-0.5 text-xs text-[var(--muted)]">
                {groundCount} nearby ground/place photo{groundCount === 1 ? "" : "s"}
              </div>
            ) : null}
          </div>
          <button type="button" className="help-q on" aria-label="Close images" onClick={onClose}>
            ×
          </button>
        </div>

        {loading ? (
          <p className="p-4 text-sm text-[var(--muted)]">Loading aerial + nearby photos…</p>
        ) : current ? (
          <div className="loc-images-stage">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={current.url} alt={current.label} className="loc-images-img" />
            <div className="loc-images-caption">
              <span>{current.label}</span>
              <span className="text-[var(--muted)]">
                {idx + 1} / {gallery.length} · {current.source}
                {current.kind === "ground" ? " · photo" : ""}
              </span>
            </div>
          </div>
        ) : (
          <p className="p-4 text-sm text-[var(--muted)]">
            {error ||
              "No coordinates on this file yet — open Intelligence after the parcel is geocoded to view imagery."}
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

        {note ? <p className="loc-images-note">{note}</p> : null}

        {maps && (maps.google_maps || maps.google_street_view) ? (
          <div className="loc-images-links">
            {maps.google_maps ? (
              <a href={maps.google_maps} target="_blank" rel="noreferrer">
                Google Maps
              </a>
            ) : null}
            {maps.google_street_view ? (
              <a href={maps.google_street_view} target="_blank" rel="noreferrer">
                Street View
              </a>
            ) : null}
            {maps.google_earth ? (
              <a href={maps.google_earth} target="_blank" rel="noreferrer">
                Google Earth
              </a>
            ) : null}
            {maps.openstreetmap ? (
              <a href={maps.openstreetmap} target="_blank" rel="noreferrer">
                OpenStreetMap
              </a>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
