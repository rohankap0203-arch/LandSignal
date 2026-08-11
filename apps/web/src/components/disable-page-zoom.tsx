"use client";

import { useEffect } from "react";

/** True when the event target is inside the Land Viewer map (Leaflet pinch-zoom). */
function isLandViewerMapTarget(target: EventTarget | null) {
  return target instanceof Element && Boolean(target.closest(".land-viewer-map"));
}

/**
 * Blocks browser/page pinch-zoom and double-tap zoom on phones so the layout
 * cannot drift out of view. Land Viewer's Leaflet map keeps its own pinch zoom.
 */
export function DisablePageZoom() {
  useEffect(() => {
    const blockGesture = (event: Event) => {
      if (isLandViewerMapTarget(event.target)) return;
      event.preventDefault();
    };

    const blockMultiTouch = (event: TouchEvent) => {
      if (event.touches.length < 2) return;
      if (isLandViewerMapTarget(event.target)) return;
      event.preventDefault();
    };

    // Safari (iOS) pinch gestures
    document.addEventListener("gesturestart", blockGesture, { passive: false });
    document.addEventListener("gesturechange", blockGesture, { passive: false });
    document.addEventListener("gestureend", blockGesture, { passive: false });
    // Multi-finger pinch on most mobile browsers
    document.addEventListener("touchmove", blockMultiTouch, { passive: false });

    // Ctrl/⌘ + wheel browser zoom (trackpads / desktop)
    const blockWheelZoom = (event: WheelEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (isLandViewerMapTarget(event.target)) return;
      event.preventDefault();
    };
    document.addEventListener("wheel", blockWheelZoom, { passive: false });

    // Ctrl/⌘ + +/- / 0 browser zoom shortcuts
    const blockKeyZoom = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      if (event.key === "+" || event.key === "=" || event.key === "-" || event.key === "_" || event.key === "0") {
        event.preventDefault();
      }
    };
    document.addEventListener("keydown", blockKeyZoom);

    return () => {
      document.removeEventListener("gesturestart", blockGesture);
      document.removeEventListener("gesturechange", blockGesture);
      document.removeEventListener("gestureend", blockGesture);
      document.removeEventListener("touchmove", blockMultiTouch);
      document.removeEventListener("wheel", blockWheelZoom);
      document.removeEventListener("keydown", blockKeyZoom);
    };
  }, []);

  return null;
}
