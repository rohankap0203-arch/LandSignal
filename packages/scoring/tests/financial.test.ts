import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  askingDiscountPct,
  breakevenLandValue,
  farmlandScenario,
  irr,
  npv,
  pricePerAcre,
} from "../src/financial.ts";

describe("financial helpers", () => {
  it("computes price per acre", () => {
    assert.equal(pricePerAcre(500_000, 100), 5000);
    assert.equal(pricePerAcre(500_000, 0), null);
  });

  it("computes asking discount vs estimate", () => {
    const d = askingDiscountPct(375_000, 510_000);
    assert.ok(d != null);
    assert.ok(Math.abs(d - -26.4705) < 0.01);
  });

  it("computes NPV and IRR for simple project", () => {
    const flows = [-100, 60, 60];
    assert.ok(Math.abs(npv(0.1, flows) - 4.132) < 0.01);
    const r = irr(flows);
    assert.ok(r != null && r > 0.13 && r < 0.14);
  });

  it("farmland scenario produces finite outputs", () => {
    const result = farmlandScenario({
      cashRentPerAcre: 220,
      acres: 80,
      vacancyRate: 0.05,
      opexPerAcre: 20,
      taxes: 4000,
      insurance: 1200,
      management: 1500,
      purchasePrice: 480_000,
      holdYears: 10,
      exitCapRate: 0.045,
      annualAppreciation: 0.03,
      discountRate: 0.1,
    });
    assert.ok(result.noi > 0);
    assert.ok(result.capRate != null);
    assert.equal(breakevenLandValue(result.noi, 0.045) != null, true);
  });
});
