"""Parent/child chunking and hybrid ranking (pure parts; the retrieval eval covers the DB path)."""
from app.services.file_processing.file_ingestion import embedding_text
from app.services.file_processing.hierarchy import (
    CHILD_MAX_CHARS,
    PARENT_MAX_CHARS,
    build_hierarchy,
    split_children,
    split_parents,
)
from app.services.rag.retriever import (
    KEYWORD_WEIGHT_IDENTIFIER,
    KEYWORD_WEIGHT_PLAIN,
    build_context,
    keyword_terms,
    keyword_weight,
    reciprocal_rank_fusion,
)

TABLE = "| Part | Price |\n|---|---|\n" + "\n".join(f"| HX-{n}-B | {n}.00 EUR |" for n in range(3000, 3200))


def test_big_table_is_bounded_and_every_piece_keeps_the_header():
    parents = split_parents(TABLE)
    assert len(parents) > 1 and all(len(p) <= PARENT_MAX_CHARS for p in parents)
    assert all(p.startswith("| Part | Price |\n|---|---|") for p in parents)
    children = [c for p in parents for c in split_children(p)]
    assert all(c.startswith("| Part | Price |") and len(c) <= CHILD_MAX_CHARS + 60 for c in children)
    rows = [line for c in children for line in c.split("\n")[2:]]
    assert len(rows) == 200 and len(set(rows)) == 200  # every row once, none lost


def test_prose_and_tables_never_share_a_parent():
    text = "Intro paragraph about parts.\n\n" + TABLE[:200] + "\n\nClosing remark."
    parents = split_parents(text)
    assert parents[0] == "Intro paragraph about parts."
    assert parents[-1] == "Closing remark."
    assert all(p.startswith("| Part") for p in parents[1:-1])


def test_long_paragraph_is_split_and_small_parent_is_its_own_child():
    long = ("word " * 800).strip()
    assert all(len(p) <= PARENT_MAX_CHARS for p in split_parents(long))
    assert split_children("short text") == ["short text"]


def test_build_hierarchy_links_children_to_parents_and_keeps_metadata():
    chunks = build_hierarchy([{"content": "A " * 900, "metadata": {"section_title": "Rules"}},
                              {"content": "", "metadata": {}}])
    keys = {c["metadata"]["parent_key"] for c in chunks}
    assert keys and all(k.startswith("0:") for k in keys)  # empty unit skipped
    for c in chunks:
        assert c["metadata"]["section_title"] == "Rules"
        assert c["content"].strip() in " ".join(c["parent_content"].split()) or c["content"] in c["parent_content"]


def test_child_is_embedded_with_its_section_title():
    assert embedding_text({"content": "Badges expire at 18:00.", "metadata": {"section_title": "Access control"}}) \
        == "Access control\nBadges expire at 18:00."
    assert embedding_text({"content": "## Access control\nText", "metadata": {"section_title": "Access control"}}) \
        == "## Access control\nText"  # title already there
    assert embedding_text({"content": "x", "metadata": {}}) == "x"


def test_rrf_rewards_agreement_and_respects_weights():
    a, b, c = {"id": 1}, {"id": 2}, {"id": 3}
    fused = reciprocal_rank_fusion([a, b, c], [b, c])
    # b: 1/62 + 1/61 beats a: 1/61 alone (top of ONE list) -> agreement wins
    assert [r["id"] for r in fused] == [2, 3, 1]
    keyword_ignored = reciprocal_rank_fusion([a, b], [b, a], weights=(1.0, 0.0))
    assert [r["id"] for r in keyword_ignored] == [1, 2]


def test_keyword_terms_and_weight():
    assert "HX-3127-C" in keyword_terms("Which bin holds HX-3127-C?")
    assert keyword_weight("What does E-7731 mean?") == KEYWORD_WEIGHT_IDENTIFIER
    assert keyword_weight("Where is the meeting place in Leipzig?") == KEYWORD_WEIGHT_PLAIN
    assert keyword_terms("") == []


def test_context_names_the_source_file_and_section():
    ctx = build_context([
        {"content": "Badges expire at 18:00.", "filename": "policy.md", "metadata": {"section_title": "Access"}},
        {"content": "  ", "filename": "x.md", "metadata": {}},
        {"content": "row", "filename": "parts.md", "metadata": {}},
    ])
    assert ctx == "Source: policy.md > Access\nBadges expire at 18:00.\n\n---\n\nSource: parts.md\nrow"
