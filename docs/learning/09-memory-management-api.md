# 09 · Memory management API + export/import (`feature/memory-management-api`)

## Memory API (replaces `/memories/test-*`)
| Endpoint | Purpose |
|---|---|
| `GET /memories?user_id=&memory_type=&include_inactive=` | List |
| `GET /memories/search?user_id=&query=&top_k=` | Semantic search (returns `distance`) |
| `POST /memories` | Add a memory manually (`source="user"`) |
| `PATCH /memories/{id}` | Edit content/type/importance/active. **New content → new embedding** |
| `DELETE /memories/{id}?hard=false` | Soft delete (deactivate, reversible); `hard=true` deletes permanently |
| `GET /memories/profile/{user_id}` | Cached profile |
| `POST /memories/profile/{user_id}/rebuild` | Recompute the profile |
| `DELETE /memories/profile/{user_id}/items?value=` | Remove a profile item that has no memory behind it |

- **Response models:** `MemoryOut` deliberately omits the 384-number embedding, because clients don't need it.
- **Validation:** `memory_type` is an enum (unknown → 422) and importance must be in 0–1.

### Design: the profile is *derived*, so edit the source
The profile isn't stored independently. It's computed from active memories, plus items extracted from messages, and cached in `user_profile_snapshot`. Editing the cache directly would be overwritten by the next background refresh, so the API edits **memories** and then rebuilds.

### Bug: deleted memories stayed in the profile
`refresh_user_profile_cache` only **merges** new data into cached items. The new `rebuild_user_profile_cache` first drops items whose `metadata.memory_id` is missing or inactive, keeps message-derived items (which have no memory id), then merges.

### Re-embedding on edit
The embedding *is* the memory's meaning for search. Change the text without re-embedding and search keeps finding it by its **old** wording. Verified: after editing "VS Code" → "Neovim", searching "neovim" finds it.

## Bug found: no long-term memory was saved after the Python 3.12 upgrade
```python
class EvidenceType(str, Enum): ...
str(EvidenceType.explicit)
# Python 3.10 → "explicit"
# Python 3.11+ → "EvidenceType.explicit"
```
The promoter did `str(item["evidence"]).lower()`, which gave `"evidencetype.explicit"`, so every memory failed its rules and nothing was promoted. The 3.12 smoke test only checked import and chat, not promotion.

**Fix:** `enum.StrEnum` (3.11+), where `str()` and f-strings return the plain value. Added `tests/test_enums.py` as a regression test.

**Lessons:**
1. Read the "What's New" notes when upgrading language versions.
2. Smoke tests must cover the critical paths, not just "it starts".
3. A test that would have caught it now exists.

### Manual memories were invisible in the profile
Profile rules require metadata (evidence, confidence, temporal scope, ...) that the LLM extractor adds automatically. A hand-added memory is by definition an explicit, durable, first-person statement, so `_manual_memory_metadata()` sets exactly that.

## Export / import
**Export** `GET /conversations/{id}/export`:
- `format` + `version` (so future changes stay readable), title, created_at
- messages with timestamps and attached **file names** (file bytes aren't exported)
- internal state (`stm`, `agent_state`) left out, because it's recomputed

**Import:**
- `POST /conversations/import?user_id=` creates a **new** conversation
- `POST /conversations/{id}/import` appends to an existing one

Fixes to import:
| Before | After |
|---|---|
| `token_count=0`, breaking the STM token window | Real tiktoken count |
| Timestamps ignored | Kept; otherwise spaced 1 ms apart to preserve order |
| Any `role` string accepted | `Literal["user","assistant"]` (422 otherwise), max 2000 messages |
| One commit per message | One transaction (`add_all`) |
| Memory pipeline never ran | `schedule_memory_maintenance_pipeline` builds LTM, metadata and profile as if chatted live |
| Missing conversation crashed | 404 |

Verified: export → import as new → re-export gives identical message order and content.
