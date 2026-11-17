# 35 — Prompts as files

Branch: `feature/prompts-as-files` (Phase F, "measure")

## What changed

Every prompt moved out of Python strings into Markdown files:

```
backend/app/prompts/
  loader.py                     load_prompt() / render_prompt()
  agents/{general,code,data,research,document,image}.md
  agents/router.md              template: {{names}} {{previous_agent}} {{default_agent}} {{recent}}
  background/<job>.{system,user}.md   memory, summary, metadata, profile prompts (13 files)
  fragments/file_output.md      the "downloadable file / templates" tool rules shared by 5 agents
```

- Agents: `instruction=load_prompt("agents/code")`.
- The router: `render_prompt("agents/router", names=..., ...)`.
- `app.prompts` still exports the same `*_PROMPT` constants, so no background call site changed.

## Why

- **A prompt is content, not code.** As a file it has a clean diff, can be reviewed by
  someone who doesn't read Python, and can be edited without touching logic.
- **One copy of shared rules.** The file-output tool block was pasted into 5 agents. Now it
  is one fragment, so a fix lands everywhere at once.
- **It sets up Phase G/H.** Tool-confirmation and compaction both change prompt wording.
  With files plus evals, each wording change is a small, measurable diff.

## Design choices

| Choice | Reason |
|---|---|
| `{{var}}` / `{{> fragment}}`, not `{var}` | Background prompts are used with Python `.format()` and contain JSON examples with `{}`. A different syntax lets them be stored **verbatim**. |
| `render_prompt` errors on missing *and* unused values | A typo like `{{previous_agnet}}` fails loudly in tests instead of shipping a literal `{{...}}` to the model. |
| Loader drops exactly one trailing newline | Editors add a final newline. Without this rule, saving a file in VS Code would silently change the prompt. |
| `lru_cache` on `load_prompt` | Files are read once per process; there is no disk I/O per turn. |

## How "no behaviour change" was proven

The rule for a refactor is that behaviour must not change. It was proven in two layers:

1. **Byte-equality.** Before the refactor, a script snapshotted all 20 rendered prompts: 13 background prompts, 6 agents, and the router with a fixed context. After the refactor the snapshot was taken again and `cmp` reported the two as **byte-identical**.
2. **Behaviour.** The eval suite (note 34) scored routing 1.0, tools 1.0 and answers 1.0, matching the baseline.

`tests/test_prompts.py` (12 tests) keeps it safe going forward:

- Each background USER prompt's `{placeholders}` must exactly equal the keywords its call site passes to `.format()`. Adding or dropping a placeholder would otherwise be a runtime `KeyError` or silently lost data.
- Every agent prompt loads, and nothing unresolved (`{{`) is left in it.
- The shared fragment is used by exactly the 5 expected agents.
- The router renders the agent names, the sticky previous agent and the history.
- The loader itself: the include, the trailing newline, and errors for missing/unused values or a missing file.
- There are no orphan `.md` files.

## Gotcha found on the way: `.gitignore` ate the prompts

The root `.gitignore` has `*.md` with a few exceptions, so `git status` simply didn't show
the new prompt files. Committing would have produced a repo that crashes on a fresh clone,
with `Prompt file not found`.

The same rule had already hidden `backend/evals/fixtures/notes.md` on the previous branch.
That fixture was never committed, so the eval cases that use it would fail on a fresh clone.

The fix whitelists source Markdown explicitly:

```
!backend/app/prompts/**/*.md
!backend/evals/fixtures/*.md
```

Lessons:

- A broad ignore pattern (`*.md`) plus "it works on my machine" is a classic trap.
- Check `git ls-files -o -i --exclude-standard`, which lists the ignored files on disk, when adding new file types.
