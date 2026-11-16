# 17 · Architecture diagram and README (`docs/architecture`)

## Why diagrams as code
The README's diagrams are **Mermaid**: plain text that GitHub renders as a diagram.
- They live in the repo, change in the same commits as the code, and show up in code review.
- A PNG drawn in a separate tool goes stale silently.

## What the README now contains
1. **Component diagram:** client, API layers, agents, the 6 MCP servers, ingestion, Postgres + pgvector, and the free external services, with arrows for who calls whom.
2. **Sequence diagram:** the life of one message (auth → memory + RAG → root routing → agent → MCP tools → streamed reply → background memory work).
3. **Key design decisions table:** each choice with its *why* (the decisions made across branches 01–16).
4. **Requirements coverage:** every assignment requirement mapped to the files that implement it.
5. **Setup, WebSocket protocol, measured free-tier limits, project structure.**

The old README was only a file tree, and an outdated one (it listed `db/models`, which no longer exists).

Also added: the root `.env.example` (for docker-compose), which the setup steps reference.
