/**
 * Supabase Built-in Embedding
 * Uses gte-small (384 dims) — no external API key needed.
 * Available natively in Supabase Edge Functions.
 */

// @ts-ignore — Supabase.ai is available in Edge Function runtime
const session = new Supabase.ai.Session("gte-small");

export async function embed(text: string): Promise<number[]> {
  const output = await session.run(text, {
    mean_pool: true,
    normalize: true,
  });

  // output is a Float32Array or number[] depending on runtime
  return Array.from(output);
}
