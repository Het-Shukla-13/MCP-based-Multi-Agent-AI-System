# 20 · Markdown replies (`feature/fe-markdown`)

## What renders now
Assistant replies go through `components/MarkdownMessage.jsx` (`react-markdown` + `remark-gfm`, MIT):
- headings, lists, bold, quotes, links;
- **GFM tables** (wrapped for horizontal scroll);
- **fenced code blocks** with a language label and a Copy button;
- **images**, including tool-generated ones.

User messages stay plain text, because what you typed is shown as typed.

## Security: no raw HTML
`react-markdown` turns Markdown into React elements and **does not render HTML found in the text**. Verified in the browser: asking the agent to repeat `<img src=x onerror=alert(1)><script>alert(2)</script>` produced **0 injected elements and 0 alerts**; the tags were shown as text.

**Never add `rehype-raw`.** The access token lives in `localStorage` (branch 18), which is only acceptable if the page never executes injected HTML.

## Generated-file links and images
The agent writes `/files/generated/<id>/download` (relative, no token). The `a`/`img` component overrides recognise exactly that path pattern and turn it into `http://<api>/files/generated/<id>/...?token=...`. Other URLs are untouched. Verified: the image loads (768×768); the same URL without a token returns 401.

## Performance
`MarkdownMessage` is wrapped in `memo`, so while one reply streams, earlier messages don't re-parse their Markdown on every chunk.

## Also
Removed the unused `uuid` dependency (the code uses the built-in `crypto.randomUUID()`).

## Found by looking at the screenshot
A reply ended with "For context: [root] called tool transfer_to_agent…": ADK's internal routing text leaking into a sub-agent's input. Fixed on the backend in `fix/adk-context-leak` (note 21).
