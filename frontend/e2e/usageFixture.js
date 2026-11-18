// Realistic usage data for deterministic usage-panel tests (dates relative to today).
const day = (offset) => {
  const d = new Date();
  d.setDate(d.getDate() - offset);
  return d.toISOString().slice(0, 10);
};

export function usageSummary(days = 7) {
  const turns = [3, 0, 7, 12, 5, 19, 9];
  const daily = Array.from({ length: days }, (_, i) => {
    const n = turns[(i + 7) % 7] ?? 0;
    return { date: day(days - 1 - i), turns: n, errors: n > 10 ? 1 : 0, tokens: n * 7100 };
  });
  return {
    days,
    turns: daily.reduce((s, d) => s + d.turns, 0),
    error_rate: 0.036,
    fallback_rate: 0.09,
    latency_ms: { ttft_p50: 1450, ttft_p95: 4300, total_p50: 4832, total_p95: 7904 },
    agents: { general: 24, document: 14, research: 9, data: 6, code: 2 },
    tools: {
      fetch_page: { calls: 18, failures: 0, p50_ms: 816 },
      create_file: { calls: 8, failures: 0, p50_ms: 4 },
      web_search: { calls: 7, failures: 1, p50_ms: 2140 },
      table_info: { calls: 5, failures: 0, p50_ms: 75 },
    },
    tokens_by_model: [
      { model: "gemini-3.1-flash-lite", calls: 140, input_tokens: 284000, output_tokens: 31000 },
      { model: "openai/gpt-oss-20b", calls: 61, input_tokens: 92000, output_tokens: 18000 },
      { model: "gemini-3.5-flash-lite", calls: 55, input_tokens: 44000, output_tokens: 1200 },
    ],
    tokens_by_purpose: [
      { purpose: "agent:document", calls: 50, tokens: 141000 },
      { purpose: "agent:general", calls: 60, tokens: 118000 },
      { purpose: "memory_extraction", calls: 30, tokens: 61000 },
      { purpose: "router", calls: 55, tokens: 45200 },
      { purpose: "stm_summarization", calls: 9, tokens: 18000 },
    ],
    daily,
    cost_usd: 0,
  };
}

export function recentTurns() {
  const now = Date.now();
  return [
    ["document", 6210, 2100, 9800, 2, false],
    ["general", 3120, 1050, 3100, 0, false],
    ["research", 11840, 3900, 15200, 3, true],
    ["general", 2480, 900, 2600, 0, false],
  ].map(([agent, total, ttft, tokens, tools, error], i) => ({
    turn_id: `t${i}`,
    agent_name: agent,
    total_ms: total,
    ttft_ms: ttft,
    input_tokens: Math.round(tokens * 0.9),
    output_tokens: Math.round(tokens * 0.1),
    tool_calls: tools,
    error,
    created_at: new Date(now - i * 3_600_000).toISOString().slice(0, 19),
  }));
}

/** Route the metrics endpoints to the fixture; returns the list of requested `days`. */
export async function mockUsage(page) {
  const requested = [];
  await page.route(/\/metrics\/summary\?/, async (route) => {
    const days = Number(new URL(route.request().url()).searchParams.get("days"));
    requested.push(days);
    await route.fulfill({ json: usageSummary(days) });
  });
  await page.route(/\/metrics\/turns\?/, (route) => route.fulfill({ json: recentTurns() }));
  return requested;
}
