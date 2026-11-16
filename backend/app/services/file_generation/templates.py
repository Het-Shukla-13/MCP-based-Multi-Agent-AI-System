"""
Document templates for create_from_template (artifacts MCP server).

The AGENT fills content fields from the conversation; the SERVER injects context
the model should not invent or format inconsistently ({date}, {title}).
"""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class DocTemplate:
    description: str
    required: tuple[str, ...]
    optional: dict[str, str] = field(default_factory=dict)  # name -> default
    body: str = ""


TEMPLATES: dict[str, DocTemplate] = {
    "report": DocTemplate(
        description="Formal report: executive summary, findings, analysis, recommendations.",
        required=("summary", "findings", "recommendations"),
        optional={"analysis": "", "data_table": "", "sources": ""},
        body="""# {title}
*Prepared {date}*

## Executive summary
{summary}

## Key findings
{findings}

{analysis_section}{data_section}## Recommendations
{recommendations}
{sources_section}""",
    ),
    "meeting_notes": DocTemplate(
        description="Meeting notes: attendees, agenda, discussion, decisions, action items.",
        required=("discussion", "action_items"),
        optional={"attendees": "Not recorded", "agenda": "", "decisions": "None recorded"},
        body="""# {title}
**Date:** {date}  
**Attendees:** {attendees}

{agenda_section}## Discussion
{discussion}

## Decisions
{decisions}

## Action items
{action_items}
""",
    ),
    "study_notes": DocTemplate(
        description="Study notes: key concepts, explanation, examples, self-test questions.",
        required=("key_concepts", "explanation"),
        optional={"examples": "", "quiz": ""},
        body="""# {title}
*Study notes, {date}*

## Key concepts
{key_concepts}

## Explanation
{explanation}
{examples_section}{quiz_section}""",
    ),
    "comparison": DocTemplate(
        description="Comparison of options: overview, comparison table, pros/cons, verdict.",
        required=("comparison_table", "verdict"),
        optional={"overview": "", "pros_cons": ""},
        body="""# {title}
*Compared {date}*

{overview_section}## Comparison
{comparison_table}

{pros_cons_section}## Verdict
{verdict}
""",
    ),
    "email": DocTemplate(
        description="Professional email draft: greeting, body, sign-off.",
        required=("recipient", "body"),
        optional={"sign_off": "Best regards"},
        body="""**Subject:** {title}

Dear {recipient},

{body}

{sign_off}
""",
    ),
}

_SECTION_HEADINGS = {
    "analysis": "Analysis", "data_table": "Data", "sources": "Sources", "agenda": "Agenda",
    "examples": "Examples", "quiz": "Check your understanding", "overview": "Overview",
    "pros_cons": "Pros and cons",
}


def describe_templates() -> str:
    lines = []
    for name, t in TEMPLATES.items():
        optional = ", ".join(t.optional) or "-"
        lines.append(f"- {name}: {t.description}\n  required: {', '.join(t.required)} | optional: {optional}")
    return "Available templates (all field values are Markdown):\n" + "\n".join(lines)


def render_template(name: str, title: str, fields: dict[str, str]) -> str:
    """Fill a template. Raises ValueError listing what is wrong (the agent can retry)."""
    if name not in TEMPLATES:
        raise ValueError(f"Unknown template '{name}'. Use one of: {', '.join(TEMPLATES)}")
    template = TEMPLATES[name]
    fields = {k: str(v).strip() for k, v in (fields or {}).items()}
    missing = [f for f in template.required if not fields.get(f)]
    if missing:
        raise ValueError(f"Missing required field(s) for '{name}': {', '.join(missing)}")

    values = {**template.optional, **{k: v for k, v in fields.items() if k in template.required or k in template.optional}}
    # Context injection: values the model must not invent or format inconsistently.
    values["title"] = title.strip() or name.replace("_", " ").title()
    values["date"] = date.today().strftime("%d %B %Y")
    # Optional sections render with their heading only when provided.
    for key, heading in _SECTION_HEADINGS.items():
        text = values.get(key, "")
        if key == "sources" and text:
            values[f"{key}_section"] = f"\n## {heading}\n{text}\n"
        else:
            values[f"{key}_section"] = f"## {heading}\n{text}\n\n" if text else ""
    return template.body.format_map(_Defaults(values)).strip() + "\n"


class _Defaults(dict):
    def __missing__(self, key):  # unknown placeholder -> empty, never KeyError
        return ""
