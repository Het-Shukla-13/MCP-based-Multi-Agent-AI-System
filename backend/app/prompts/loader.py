"""
Prompts live in Markdown files next to this module, not in Python strings.

Why: a prompt is content, not code. As a file it gets a readable diff, can be
reviewed by someone who doesn't read Python, and can be edited without touching
logic. The eval suite (evals/) is the safety net for every prompt edit.

Two syntaxes, deliberately different from Python's ``str.format`` braces so the
background prompts (which call ``.format(...)`` and contain JSON examples) are
stored verbatim:

- ``{{name}}``          -> value passed to ``render_prompt(..., name=...)``
- ``{{> fragment}}``    -> contents of ``fragments/<fragment>.md`` (shared text)

Every file ends with one trailing newline (editor/POSIX friendly); the loader
drops exactly one so the rendered text is byte-identical to what was written.
"""
import re
from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).parent

_INCLUDE = re.compile(r"\{\{>\s*([\w-]+)\s*\}\}")
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class PromptError(KeyError):
    pass


@lru_cache(maxsize=None)
def load_prompt(name: str) -> str:
    """Raw text of ``<name>.md`` (e.g. ``"agents/code"``), includes resolved."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise PromptError(f"Prompt file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if text.endswith("\n"):
        text = text[:-1]
    return _INCLUDE.sub(lambda m: load_prompt(f"fragments/{m.group(1)}"), text)


def render_prompt(name: str, **values: object) -> str:
    """``load_prompt`` + ``{{var}}`` substitution. Missing/unused values are errors."""
    text = load_prompt(name)
    wanted = set(_VAR.findall(text))
    missing, unused = wanted - values.keys(), values.keys() - wanted
    if missing or unused:
        raise PromptError(f"{name}: missing={sorted(missing)} unused={sorted(unused)}")
    return _VAR.sub(lambda m: str(values[m.group(1)]), text)
