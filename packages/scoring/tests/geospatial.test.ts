import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  acresFromSquareMeters,
  buildableAcreageEstimate,
  haversineMeters,
  ringAreaSquareMeters,
  usableAgAcreageEstimate,
} from "../src/geospatial.ts";

describe("geospatial helpers", () => {
  it("haversine distance roughly matches known city pair", () => {
    // NYC to Philly ~130km
    const d = haversineMeters(40.7128, -74.006, 39.9526, -75.1652);
    assert.ok(d > 120_000 && d < 150_000);
  });

  it("computes ring area for approximate 1km square", () => {
    const lat = 40;
    const dLat = 1 / 111;
    const dLon = 1 / (111 * Math.cos((lat * Math.PI) / 180));
    const ring: [number, number][] = [
      [0, lat],
      [dLon, lat],
      [dLon, lat + dLat],
      [0, lat + dLat],
      [0, lat],
    ];
    const m2 = ringAreaSquareMeters(ring);
    assert.ok(m2 > 900_000 && m2 < 1_100_000);
    assert.ok(acresFromSquareMeters(m2) > 220 && acresFromSquareMeters(m2) < 280);
  });

  it("does not invent buildable acres when wetland/flood unknown", () => {
    assert.equal(
      buildableAcreageEstimate({
        acreage: 100,
        wetlandPct: null,
        floodPct: 10,
        extremeSlopePctOfParcel: 5,
      }),
      null,
    );
  });

  it("estimates usable ag acres with wetland drag", () => {
    const acres = usableAgAcreageEstimate({
      acreage: 100,
      wetlandPct: 20,
      primeFarmlandPct: 80,
      maxSlopePct: 4,
    });
    assert.ok(acres != null && acres < 100 && acres > 50);
  });
});
