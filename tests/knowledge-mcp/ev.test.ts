import { assertEquals } from "jsr:@std/assert";
import { calculateLiveEV } from "../../supabase/functions/_shared/ev.ts";

Deno.test("base EV is confidence * impact for fresh entry", () => {
  const ev = calculateLiveEV(0.9, 0.8, new Date().toISOString(), "erp", null);
  const expected = 0.9 * 0.8 * 1.0;
  assertEquals(Math.abs(ev - expected) < 0.001, true);
});

Deno.test("expired TTL returns zero", () => {
  const oldDate = new Date(
    Date.now() - 100 * 24 * 60 * 60 * 1000,
  ).toISOString();
  const ev = calculateLiveEV(0.9, 0.9, oldDate, "ai", 30);
  assertEquals(ev, 0);
});

Deno.test("AI domain decays faster than ERP", () => {
  const sixWeeksAgo = new Date(
    Date.now() - 42 * 24 * 60 * 60 * 1000,
  ).toISOString();
  const aiEV = calculateLiveEV(0.9, 0.9, sixWeeksAgo, "ai", null);
  const erpEV = calculateLiveEV(0.9, 0.9, sixWeeksAgo, "erp", null);
  assertEquals(erpEV > aiEV, true, "ERP should decay slower than AI");
});

Deno.test("unknown domain uses general decay rate", () => {
  const ev = calculateLiveEV(
    1.0,
    1.0,
    new Date().toISOString(),
    "unknown_domain",
    null,
  );
  assertEquals(Math.abs(ev - 1.0) < 0.01, true);
});

Deno.test("zero confidence gives zero EV", () => {
  const ev = calculateLiveEV(0, 0.9, new Date().toISOString(), "ai", null);
  assertEquals(ev, 0);
});
