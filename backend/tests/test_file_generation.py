import fitz
import pytest

from app.services.file_generation.file_renderer import render_markdown_pdf
from app.services.file_generation.templates import TEMPLATES, render_template


def test_markdown_pdf_renders_structure_not_raw_markdown():
    pdf = render_markdown_pdf("Report", "## Summary\nRevenue **grew**.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n")
    text = fitz.open("pdf", pdf)[0].get_text()
    assert "Summary" in text and "Revenue" in text
    assert "##" not in text and "|---" not in text


def test_template_injects_title_and_date_and_optional_sections():
    md = render_template("report", "Q3 Sales", {
        "summary": "Revenue grew.", "findings": "- North led", "recommendations": "- Expand North",
        "sources": "- sales.csv", "unknown_field": "ignored",
    })
    assert md.startswith("# Q3 Sales")
    assert "*Prepared " in md                      # injected date
    assert "## Sources\n- sales.csv" in md         # optional section rendered
    assert "## Analysis" not in md                 # empty optional section omitted
    assert "ignored" not in md                     # unknown fields dropped


def test_template_reports_missing_required_fields():
    with pytest.raises(ValueError, match="findings, recommendations"):
        render_template("report", "X", {"summary": "s"})


def test_every_template_renders_with_required_fields():
    for name, t in TEMPLATES.items():
        md = render_template(name, "T", {f: f"value-{f}" for f in t.required})
        assert all(f"value-{f}" in md for f in t.required), name


def test_title_with_extension_is_not_doubled():
    from app.mcp_servers.artifacts_server import file_stem

    assert file_stem("green-tea.md") == "green-tea"
    assert file_stem("Report.PDF") == file_stem("Report")
    assert file_stem("v1.2 release notes") == file_stem("v1.2 release notes")  # not an extension
