# 23 · Stale profile items after editing a memory (`fix/profile-stale-items`)

**Found by:** the memory-panel browser test (note 24). After editing a memory, the Profile tab showed **both** the old and the new wording.

**Cause:** `rebuild_user_profile_cache` (note 09) dropped items whose memory was deleted or inactive, but an *edited* memory is still active, so its **old** item stayed and the merge added the new one.

**Fix:** memory-derived items (they carry `metadata.memory_id`) are now **always recomputed** from the current active memories. Only message-derived items (no memory behind them) are carried over. A unit test covers edited, deleted and message-derived items.

**Lesson:** a cache rebuild should start from the source of truth, not patch the old cache. Patching means every kind of change (delete, deactivate, *edit*) needs its own invalidation rule, and one gets forgotten.
