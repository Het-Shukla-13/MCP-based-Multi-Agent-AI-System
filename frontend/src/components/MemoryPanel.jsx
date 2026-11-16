import { useCallback, useEffect, useState } from "react";
import {
  createMemory,
  errorMessage,
  fetchProfile,
  listMemories,
  rebuildProfile,
  removeMemory,
  removeProfileItem,
  searchMemories,
  updateMemory,
} from "../lib/api";

const MEMORY_TYPES = ["preference", "fact", "decision", "task"];
const PROFILE_SECTIONS = [
  ["preferences", "Preferences"],
  ["facts", "Facts"],
  ["active_goals", "Active goals"],
  ["decisions", "Decisions"],
];

function MemoryRow({ memory, onChanged, onError }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(memory.content);
  const [busy, setBusy] = useState(false);

  const run = async (action) => {
    setBusy(true);
    try {
      await action();
      await onChanged();
    } catch (err) {
      onError(errorMessage(err, "Memory update failed."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className={`memory-row${memory.is_active ? "" : " memory-row--inactive"}`}>
      <div className="memory-row__meta">
        <span className={`memory-type memory-type--${memory.memory_type}`}>{memory.memory_type}</span>
        <span>importance {memory.importance_score.toFixed(2)}</span>
        {memory.distance != null ? <span>distance {memory.distance.toFixed(3)}</span> : null}
        {memory.source === "user" ? <span>added by you</span> : null}
        {!memory.is_active ? <span>inactive</span> : null}
      </div>
      {editing ? (
        <textarea className="memory-edit" onChange={(e) => setDraft(e.target.value)} rows={2} value={draft} />
      ) : (
        <p className="memory-row__content">{memory.content}</p>
      )}
      <div className="memory-row__actions">
        {editing ? (
          <>
            <button disabled={busy || !draft.trim()} onClick={() => run(async () => { await updateMemory(memory.id, { content: draft.trim() }); setEditing(false); })} type="button">Save</button>
            <button disabled={busy} onClick={() => { setDraft(memory.content); setEditing(false); }} type="button">Cancel</button>
          </>
        ) : (
          <>
            <button disabled={busy} onClick={() => setEditing(true)} type="button">Edit</button>
            {memory.is_active ? (
              <button disabled={busy} onClick={() => run(() => removeMemory(memory.id))} title="Hide from the assistant (reversible)" type="button">Deactivate</button>
            ) : (
              <button disabled={busy} onClick={() => run(() => updateMemory(memory.id, { is_active: true }))} type="button">Reactivate</button>
            )}
            <button
              className="danger"
              disabled={busy}
              onClick={() => window.confirm("Delete this memory permanently?") && run(() => removeMemory(memory.id, { hard: true }))}
              type="button"
            >
              Delete
            </button>
          </>
        )}
      </div>
    </li>
  );
}

function MemoriesTab({ onError }) {
  const [memories, setMemories] = useState([]);
  const [query, setQuery] = useState("");
  const [isSearch, setIsSearch] = useState(false);
  const [showInactive, setShowInactive] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [newType, setNewType] = useState("preference");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = isSearch && query.trim()
        ? await searchMemories(query.trim())
        : await listMemories({ includeInactive: showInactive });
      setMemories(data);
    } catch (err) {
      onError(errorMessage(err, "Could not load memories."));
    } finally {
      setLoading(false);
    }
  }, [isSearch, query, showInactive, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  const add = async (event) => {
    event.preventDefault();
    if (!newContent.trim()) return;
    try {
      await createMemory(newContent.trim(), newType);
      setNewContent("");
      await load();
    } catch (err) {
      onError(errorMessage(err, "Could not add the memory."));
    }
  };

  return (
    <div className="memory-tab">
      <form className="memory-search" onSubmit={(e) => { e.preventDefault(); setIsSearch(Boolean(query.trim())); }}>
        <input onChange={(e) => { setQuery(e.target.value); if (!e.target.value) setIsSearch(false); }} placeholder="Search by meaning, e.g. 'favourite tools'" value={query} />
        <button type="submit">Search</button>
      </form>
      <label className="memory-toggle">
        <input checked={showInactive} disabled={isSearch} onChange={(e) => setShowInactive(e.target.checked)} type="checkbox" /> show inactive
      </label>

      {loading ? <p className="sidebar__hint">Loading...</p> : null}
      {!loading && memories.length === 0 ? <p className="sidebar__hint">{isSearch ? "No matching memories." : "No memories yet. They are learned from your chats, or add one below."}</p> : null}
      <ul className="memory-list">
        {memories.map((m) => <MemoryRow key={m.id} memory={m} onChanged={load} onError={onError} />)}
      </ul>

      <form className="memory-add" onSubmit={add}>
        <p>Teach the assistant something</p>
        <textarea onChange={(e) => setNewContent(e.target.value)} placeholder="e.g. I prefer concise answers with code examples." rows={2} value={newContent} />
        <div>
          <select onChange={(e) => setNewType(e.target.value)} value={newType}>
            {MEMORY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <button className="primary-button" disabled={!newContent.trim()} type="submit">Add memory</button>
        </div>
      </form>
    </div>
  );
}

function ProfileTab({ onError }) {
  const [profile, setProfile] = useState(null);

  const load = useCallback(
    (rebuild = false) =>
      (rebuild ? rebuildProfile() : fetchProfile())
        .then(setProfile) // state is set when the request resolves, not synchronously
        .catch((err) => onError(errorMessage(err, "Could not load the profile."))),
    [onError]
  );

  useEffect(() => {
    void load();
  }, [load]);

  if (!profile) return <p className="sidebar__hint">Loading...</p>;
  const empty = PROFILE_SECTIONS.every(([key]) => !profile[key]?.length);

  return (
    <div className="memory-tab">
      <p className="memory-note">Built automatically from your active memories. Edit or delete memories to change it.</p>
      {empty ? <p className="sidebar__hint">Nothing learned yet.</p> : null}
      {PROFILE_SECTIONS.map(([key, title]) =>
        profile[key]?.length ? (
          <section className="profile-section" key={key}>
            <h4>{title}</h4>
            <ul>
              {profile[key].map((item) => (
                <li key={item}>
                  <span>{item}</span>
                  <button
                    aria-label={`Remove ${item}`}
                    onClick={async () => {
                      try { setProfile(await removeProfileItem(item)); } catch (err) { onError(errorMessage(err, "Could not remove the item.")); }
                    }}
                    type="button"
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null
      )}
      <button className="secondary-button" onClick={() => load(true)} type="button">Rebuild profile</button>
    </div>
  );
}

export default function MemoryPanel({ onClose }) {
  const [tab, setTab] = useState("memories");
  const [error, setError] = useState("");

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="drawer-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <aside aria-label="Memory" className="drawer" role="dialog">
        <header className="drawer__header">
          <h3>What the assistant remembers</h3>
          <button aria-label="Close" onClick={onClose} type="button">✕</button>
        </header>
        <div className="drawer__tabs" role="tablist">
          <button aria-selected={tab === "memories"} onClick={() => setTab("memories")} role="tab" type="button">Memories</button>
          <button aria-selected={tab === "profile"} onClick={() => setTab("profile")} role="tab" type="button">Profile</button>
        </div>
        {error ? <p className="auth-error" role="alert">{error}</p> : null}
        {tab === "memories" ? <MemoriesTab onError={setError} /> : <ProfileTab onError={setError} />}
      </aside>
    </div>
  );
}
