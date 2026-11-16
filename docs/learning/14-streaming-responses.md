# 14 · Streaming replies (`feature/streaming-responses`)

## Concept
Without streaming, the user stares at nothing until the whole reply exists. With streaming, text appears as the model generates it. It's the same total work, but much better *perceived* speed.

## How ADK streams (verified by experiment)
`runner.run_async(..., run_config=RunConfig(streaming_mode=StreamingMode.SSE))` yields:
- events with `partial=True`, each carrying only the **new** text piece;
- then one event with `partial=False` carrying the **complete** text.

So:
- **Deltas → browser:** `emit_text_delta` forwards each partial piece as a status event `{"status":"delta","agent":..,"text":..}`.
- **Saved reply = non-partial events only.** Adding partials *and* the final event would duplicate every reply.
- **The router's own text is never streamed**, only the chosen agent's.

`STREAMING_ENABLED` (default true) switches between SSE and NONE.

## WebSocket protocol now
```
→ {"content": "..."}
← {"type":"agent_status","data":{"status":"routing","agent":"root"}}
← {"type":"agent_status","data":{"status":"working","agent":"code"}}
← {"type":"agent_status","data":{"status":"tool","agent":"code","tool":"analyze_code"}}
← {"type":"chat_delta","data":{"agent":"code","text":"Here is"}}      (many)
← {"type":"chat","data":{ "ai_message": {...complete, saved...}, ...}}
```
The client shows a draft from the deltas and replaces it with the final `chat` message, which is the saved source of truth.

## Measure before optimising
The first test showed the first delta only ~0.6s before the end, so streaming can't help if the wait is *before* the agent starts. Stage timings from the logs:
- `update_profile_snapshot` = **1.2s**: an LLM extraction call, awaited before every reply even though the reply doesn't need it.
- Router + agent ≈ 5.3s, with high variance from provider load (we saw `503 high demand` during testing).
- Gemini "thinking" was *not* the cause: default config ≈ 1.0s, forcing `thinking_level=minimal` was slower.

**Fix:** `schedule_profile_snapshot_update` runs the extraction as a background task with its own DB session. The task is kept in a set so it isn't garbage-collected before finishing.

| | First text | Full reply |
|---|---|---|
| Routed, before → after | 6.7s → **4.5s** | 7.3s → **5.3s** |
| `@code`, before → after | 4.3s → **2.8s** | 5.6s → **3.9s** |

Verified: joined deltas == saved reply, character for character (877/877, 1755/1755).
