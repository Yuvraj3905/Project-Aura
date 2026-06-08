import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ML_SERVICE_URL = process.env.ML_SERVICE_URL ?? "http://ml-service:8100";

/**
 * Parse a "input,output" price string (USD per 1,000,000 tokens) into a number pair.
 * Falls back to the given defaults if the env var is missing or malformed.
 */
function price(env: string | undefined, dIn: number, dOut: number): [number, number] {
  const [i, o] = (env ?? "").split(",").map((x) => parseFloat(x.trim()));
  return [Number.isFinite(i) ? i : dIn, Number.isFinite(o) ? o : dOut];
}

// Comparison models. Prices come from env (see .env.example) so they can track OpenAI's
// pricing without a code change; the defaults are illustrative published figures.
const MODELS = [
  { name: "gpt-4o", price: price(process.env.OPENAI_PRICE_GPT_4O, 2.5, 10.0) },
  { name: "gpt-4o-mini", price: price(process.env.OPENAI_PRICE_GPT_4O_MINI, 0.15, 0.6) },
  { name: "gpt-3.5-turbo", price: price(process.env.OPENAI_PRICE_GPT_35_TURBO, 0.5, 1.5) },
];

const PER = 1_000_000; // prices are quoted per 1M tokens

interface Stats {
  prompt_tokens: number;
  completion_tokens: number;
  saved_prompt_tokens: number;
  saved_completion_tokens: number;
  [k: string]: number;
}

function costUSD(p: number, c: number, [inP, outP]: [number, number]): number {
  return (p / PER) * inP + (c / PER) * outP;
}

/**
 * LLM usage + cost analytics. Reads raw aggregates from ml-service /usage, then layers
 * OpenAI/ChatGPT pricing on top to estimate (a) what the tokens actually generated would
 * have cost on a paid API, and (b) what the cache saved by avoiding re-generation.
 * Aura's real spend is $0 — inference is local.
 */
export async function GET() {
  let stats: Stats;
  try {
    const res = await fetch(`${ML_SERVICE_URL}/usage`, { cache: "no-store" });
    if (!res.ok) throw new Error(String(res.status));
    stats = (await res.json()) as Stats;
  } catch {
    return NextResponse.json({ error: "usage unavailable" }, { status: 502 });
  }

  const comparison = MODELS.map((m) => ({
    model: m.name,
    input_per_million: m.price[0],
    output_per_million: m.price[1],
    // What the actually-generated tokens would have cost on this model.
    est_cost_usd: +costUSD(stats.prompt_tokens, stats.completion_tokens, m.price).toFixed(4),
    // What the cache saved (tokens it avoided regenerating) priced on this model.
    saved_by_cache_usd: +costUSD(
      stats.saved_prompt_tokens,
      stats.saved_completion_tokens,
      m.price,
    ).toFixed(4),
  }));

  return NextResponse.json({ stats, comparison, local_cost_usd: 0 });
}
