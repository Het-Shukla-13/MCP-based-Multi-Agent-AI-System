import { Fragment, useEffect, useRef, useState } from "react";
import { Clock, MessageSquareText, Search, Type } from "lucide-react";
import { errorMessage, searchConversations } from "../lib/api";

const DEBOUNCE_MS = 200;
const MIN_CHARS = 2;
const HL_START = "\x01";
const HL_END = "\x02";

/** "...trip to \x01Lisbon\x02..." -> text with <mark>s. No innerHTML anywhere. */
function Highlighted({ text }) {
  const parts = [];
  let rest = text;
  let key = 0;
  while (rest) {
    const start = rest.indexOf(HL_START);
    if (start < 0) {
      parts.push(<Fragment key={key++}>{rest}</Fragment>);
      break;
    }
    const end = rest.indexOf(HL_END, start);
    parts.push(<Fragment key={key++}>{rest.slice(0, start)}</Fragment>);
    parts.push(<mark key={key++}>{rest.slice(start + 1, end < 0 ? undefined : end)}</mark>);
    rest = end < 0 ? "" : rest.slice(end + 1);
  }
  return <>{parts}</>;
}

/**
 * ⌘K / Ctrl+K: search conversations by what was said in them.
 * Combobox pattern: focus stays in the input; ↑/↓ move aria-activedescendant,
 * Enter opens, Esc closes and returns focus to where it was.
 */
export default function SearchPalette({ conversations, onClose, onOpen }) {
  const [query, setQuery] = useState("");
  const [found, setFound] = useState({ query: "", results: [], error: "" });
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const returnFocusRef = useRef(document.activeElement);

  useEffect(() => {
    inputRef.current?.focus();
    const returnTo = returnFocusRef.current;
    return () => returnTo?.focus?.();
  }, []);

  // Debounced search; each new query aborts the previous request, so a slow old
  // response can never overwrite a newer one.
  useEffect(() => {
    const q = query.trim();
    if (q.length < MIN_CHARS) return undefined;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      try {
        const results = await searchConversations(q, { signal: controller.signal });
        setFound({ query: q, results, error: "" });
        setActive(0);
      } catch (error) {
        if (!controller.signal.aborted) setFound({ query: q, results: [], error: errorMessage(error, "Search failed.") });
      }
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query]);

  const typed = query.trim();
  const recent = typed.length < MIN_CHARS;
  const items = recent
    ? conversations.slice(0, 8).map((c) => ({ conversation_id: c.id, title: c.title, match: "recent", snippet: null, message_id: null }))
    : found.query === typed
      ? found.results
      : [];
  const searching = !recent && found.query !== typed;
  const current = Math.min(active, Math.max(items.length - 1, 0));

  const onKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!items.length) return;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((current + step + items.length) % items.length);
    } else if (event.key === "Enter" && items[current]) {
      event.preventDefault();
      onOpen(items[current]);
    } else if (event.key === "Tab") {
      event.preventDefault(); // the input is the only stop: focus can't leave the dialog
    }
  };

  const optionId = (index) => `search-option-${index}`;
  const Icon = (item) => (item.match === "recent" ? Clock : item.match === "title" ? Type : MessageSquareText);

  return (
    <div className="palette-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div aria-label="Search conversations" aria-modal="true" className="palette" role="dialog">
        <div className="palette__field">
          <Search aria-hidden="true" size={18} />
          <input
            aria-activedescendant={items.length ? optionId(current) : undefined}
            aria-autocomplete="list"
            aria-controls="search-results"
            aria-expanded="true"
            aria-label="Search conversations"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search what was said in your chats..."
            ref={inputRef}
            role="combobox"
            value={query}
          />
          <kbd>Esc</kbd>
        </div>

        <p className="palette__status" role="status">
          {recent
            ? "Recent conversations"
            : searching
              ? "Searching..."
              : found.error || (items.length ? `${items.length} result${items.length > 1 ? "s" : ""}` : "No matches")}
        </p>

        <ul className="palette__results" id="search-results" role="listbox">
          {items.map((item, index) => {
            const ItemIcon = Icon(item);
            return (
              <li
                aria-selected={index === current}
                className={`palette__item${index === current ? " palette__item--active" : ""}`}
                id={optionId(index)}
                key={`${item.conversation_id}-${item.message_id || item.match}`}
                onMouseDown={(e) => {
                  e.preventDefault(); // keep focus in the input
                  onOpen(item);
                }}
                onMouseEnter={() => setActive(index)}
                role="option"
              >
                <ItemIcon aria-hidden="true" className="palette__icon" size={16} />
                <span className="palette__text">
                  <span className="palette__title">{item.title}</span>
                  {item.snippet ? (
                    <span className="palette__snippet">
                      {item.role === "assistant" ? "Assistant: " : item.role === "user" ? "You: " : ""}
                      <Highlighted text={item.snippet} />
                    </span>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ul>
        <p className="palette__hint" aria-hidden="true">
          <kbd>↑</kbd> <kbd>↓</kbd> to move · <kbd>Enter</kbd> to open
        </p>
      </div>
    </div>
  );
}
