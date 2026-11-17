"""Code MCP server: static analysis (structure, syntax errors, metrics). Never executes code."""

import asyncio
import ast
import os

from mcp.server.fastmcp import FastMCP
from tree_sitter_language_pack import get_parser

from app.mcp_servers.common import configure_server_logging, resolve_owned_file, truncate
from app.services.file_processing.file_chunkers import EXTENSION_LANGUAGE_MAP

configure_server_logging("code")
mcp = FastMCP("code")

DEFINITION_TYPES = {
    "function_definition", "class_definition", "function_declaration", "class_declaration",
    "method_definition", "method_declaration", "arrow_function", "interface_declaration",
}
LANGUAGE_ALIASES = {"py": "python", "js": "javascript", "ts": "typescript", "c++": "cpp", "golang": "go"}


def _node_name(node, source: bytes) -> str:
    name = node.child_by_field_name("name")
    return source[name.start_byte:name.end_byte].decode("utf-8", "replace") if name else "(anonymous)"


def _analyze(code: str, language: str) -> str:
    language = LANGUAGE_ALIASES.get(language.lower(), language.lower())
    source = code.encode("utf-8")
    try:
        tree = get_parser(language).parse(source)
    except Exception:
        return f"Unsupported language '{language}'. Supported: {sorted(set(EXTENSION_LANGUAGE_MAP.values()))}"

    outline, errors = [], []

    def walk(node, depth=0):
        if node.type in DEFINITION_TYPES:
            outline.append(f"{'  ' * depth}- {node.type.replace('_', ' ')} `{_node_name(node, source)}` (line {node.start_point[0] + 1})")
            depth += 1
        if node.type == "ERROR" or node.is_missing:
            errors.append(f"line {node.start_point[0] + 1}, col {node.start_point[1] + 1}: "
                          f"{'missing ' + node.type if node.is_missing else 'syntax error'}")
        for child in node.children:
            walk(child, depth)

    walk(tree.root_node)

    # Python: the real compiler gives precise messages.
    if language == "python":
        try:
            ast.parse(code)
        except SyntaxError as exc:
            errors = [f"line {exc.lineno}, col {exc.offset}: {exc.msg}"]

    lines = code.splitlines()
    comment_prefix = "#" if language == "python" else "//"
    metrics = (f"lines: {len(lines)}, blank: {sum(1 for l in lines if not l.strip())}, "
               f"comment: {sum(1 for l in lines if l.strip().startswith(comment_prefix))}, "
               f"definitions: {len(outline)}")
    return truncate(
        f"Language: {language}\nMetrics: {metrics}\n\n"
        f"Syntax: {'OK' if not errors else str(len(errors)) + ' problem(s)'}\n"
        + "\n".join(f"- {e}" for e in errors[:20])
        + "\n\nStructure:\n" + ("\n".join(outline) or "(no functions/classes)")
    )


@mcp.tool()
async def analyze_code(code: str = "", language: str = "python", file_name: str = "",
                       user_id: str = "", conversation_id: str = "") -> str:
    """Static analysis of source code: structure outline (classes/functions with line numbers),
    syntax errors and basic metrics. Pass either `code` + `language`, or the `file_name` of an
    uploaded code file. The code is never executed. user_id/conversation_id are filled in automatically."""
    if file_name:
        target, error = await resolve_owned_file(user_id, conversation_id, file_name)
        if target is None:
            return error
        ext = os.path.splitext(target.filename)[1].lower()
        language = EXTENSION_LANGUAGE_MAP.get(ext, language)
        with open(target.storage_path, encoding="utf-8", errors="replace") as fh:
            code = fh.read()
    if not code.strip():
        return "Provide `code` or the `file_name` of an uploaded code file."
    return await asyncio.to_thread(_analyze, code, language)


if __name__ == "__main__":
    mcp.run()
