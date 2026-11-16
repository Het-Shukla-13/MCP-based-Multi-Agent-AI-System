"""Backend @agent mention parsing (the frontend dropdown is optional, not required)."""

import re

# "@name" at the start or after whitespace, followed by a word boundary. The
# lookbehind stops e-mail addresses like "me@code.dev" from triggering.
_MENTION = re.compile(r"(?<!\S)@([a-zA-Z_]+)\b")


def parse_agent_mention(text: str, valid_agents: set[str]) -> tuple[str | None, str]:
    """
    Return (agent_name, text_without_mention) for the first @mention of a known agent.
    Unknown names (e.g. "@john") are left untouched and return (None, text).
    """
    for match in _MENTION.finditer(text or ""):
        name = match.group(1).lower()
        if name in valid_agents:
            cleaned = (text[: match.start()] + text[match.end():]).strip()
            cleaned = re.sub(r"\s{2,}", " ", cleaned)
            return name, cleaned or text.strip()
    return None, text
