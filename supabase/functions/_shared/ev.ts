/**
 * Expected Value Engine
 * EV = confidence × impact × freshness_decay
 * Decay is domain-specific: AI knowledge decays fast, ERP knowledge is stable.
 */

const DECAY_RATES: Record<string, number> = {
  ai: 0.05, // 5% per week — landscape moves fast
  fishing: 0.001, // nearly stable — regulations change annually
  erp: 0.005, // very stable — implementation patterns endure
  personal: 0.01,
  stanford: 0.01,
  business: 0.02,
  general: 0.02,
};

export function calculateLiveEV(
  confidence: number,
  impact: number,
  createdAt: string,
  domain: string,
  ttlDays: number | null,
): number {
  const ageMs = Date.now() - new Date(createdAt).getTime();
  const ageDays = ageMs / (24 * 60 * 60 * 1000);

  // TTL expiration: EV drops to zero
  if (ttlDays !== null && ageDays > ttlDays) return 0;

  const ageWeeks = ageDays / 7;
  const decayRate = DECAY_RATES[domain] || DECAY_RATES.general;
  const freshness = Math.pow(1 - decayRate, ageWeeks);

  return confidence * impact * freshness;
}
