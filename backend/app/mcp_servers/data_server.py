"""
Data MCP server: safe pandas analysis of the user's CSV/XLSX uploads.

Deliberately NO "run this pandas code" tool: executing model-written code on the
server would be remote code execution. Each tool is a fixed, validated operation.
"""

import asyncio
import os

import pandas as pd
from mcp.server.fastmcp import FastMCP

from app.mcp_servers.common import configure_server_logging, resolve_owned_file, truncate
from app.services.file_processing.tabular import read_csv_robust

configure_server_logging("data")
mcp = FastMCP("data")

AGGREGATIONS = {"sum", "mean", "median", "min", "max", "count", "nunique", "std"}
OPERATORS = {"==", "!=", ">", ">=", "<", "<=", "contains"}
MAX_ROWS_OUT = 50


async def _load(user_id: str, conversation_id: str, file_name: str, sheet: str = "") -> tuple[pd.DataFrame | None, str]:
    target, error = await resolve_owned_file(user_id, conversation_id, file_name)
    if target is None:
        return None, error
    # File parsing runs in a thread so concurrent calls to this server keep moving.
    return await asyncio.to_thread(_read_table, target.storage_path, target.filename, sheet)


def _read_table(path: str, filename: str, sheet: str) -> tuple[pd.DataFrame | None, str]:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".csv":
        return read_csv_robust(path), ""
    if ext == ".xlsx":
        sheets = pd.ExcelFile(path).sheet_names
        name = sheet or sheets[0]
        if name not in sheets:
            return None, f"Sheet '{sheet}' not found. Sheets: {', '.join(sheets)}"
        return pd.read_excel(path, sheet_name=name), ""
    return None, f"'{filename}' is not a CSV/XLSX file."


def _check_columns(df: pd.DataFrame, *columns: str) -> str:
    missing = [c for c in columns if c and c not in df.columns]
    return f"Unknown column(s): {missing}. Columns are: {list(df.columns)}" if missing else ""


def _table(df: pd.DataFrame) -> str:
    return truncate(df.head(MAX_ROWS_OUT).to_markdown(index=False) if len(df) else "(no rows)")


@mcp.tool()
async def table_info(file_name: str, sheet: str = "", user_id: str = "", conversation_id: str = "") -> str:
    """Overview of a CSV/XLSX file: row/column counts, column types, missing values, sample rows
    and (for XLSX) sheet names. Call this first. user_id/conversation_id are filled in automatically."""
    df, error = await _load(user_id, conversation_id, file_name, sheet)
    if df is None:
        return error
    info = pd.DataFrame({"column": df.columns, "dtype": [str(t) for t in df.dtypes],
                         "missing": df.isna().sum().values, "unique": df.nunique().values})
    return (f"Rows: {len(df)}, Columns: {df.shape[1]}\n\n{info.to_markdown(index=False)}"
            f"\n\nFirst rows:\n{df.head(5).to_markdown(index=False)}")


@mcp.tool()
async def aggregate(file_name: str, column: str, operation: str, group_by: str = "", sheet: str = "",
                    user_id: str = "", conversation_id: str = "") -> str:
    """Aggregate a column: operation is one of sum, mean, median, min, max, count, nunique, std.
    Optionally group_by another column. user_id/conversation_id are filled in automatically."""
    if operation not in AGGREGATIONS:
        return f"operation must be one of {sorted(AGGREGATIONS)}"
    df, error = await _load(user_id, conversation_id, file_name, sheet)
    if df is None:
        return error
    if error := _check_columns(df, column, group_by):
        return error
    if group_by:
        result = df.groupby(group_by)[column].agg(operation).reset_index().sort_values(column, ascending=False)
        return _table(result)
    return f"{operation}({column}) = {df[column].agg(operation)}"


@mcp.tool()
async def filter_rows(file_name: str, column: str, operator: str, value: str, limit: int = 20, sheet: str = "",
                      user_id: str = "", conversation_id: str = "") -> str:
    """Rows where `column <operator> value`. operator: ==, !=, >, >=, <, <=, contains.
    Returns the match count and up to `limit` rows. user_id/conversation_id are filled in automatically."""
    if operator not in OPERATORS:
        return f"operator must be one of {sorted(OPERATORS)}"
    df, error = await _load(user_id, conversation_id, file_name, sheet)
    if df is None:
        return error
    if error := _check_columns(df, column):
        return error
    series = df[column]
    if operator == "contains":
        mask = series.astype(str).str.contains(value, case=False, na=False, regex=False)
    else:
        target = value
        if pd.api.types.is_numeric_dtype(series):
            try:
                target = float(value)
            except ValueError:
                return f"'{column}' is numeric; '{value}' is not a number."
        mask = {"==": series == target, "!=": series != target, ">": series > target,
                ">=": series >= target, "<": series < target, "<=": series <= target}[operator]
    matched = df[mask]
    return f"{len(matched)} matching rows.\n\n" + _table(matched.head(max(1, min(limit, MAX_ROWS_OUT))))


@mcp.tool()
async def top_n(file_name: str, column: str, n: int = 10, ascending: bool = False, sheet: str = "",
                user_id: str = "", conversation_id: str = "") -> str:
    """The n rows with the largest (or smallest, ascending=true) values of a column.
    user_id/conversation_id are filled in automatically."""
    df, error = await _load(user_id, conversation_id, file_name, sheet)
    if df is None:
        return error
    if error := _check_columns(df, column):
        return error
    return _table(df.sort_values(column, ascending=ascending).head(max(1, min(n, MAX_ROWS_OUT))))


@mcp.tool()
async def value_counts(file_name: str, column: str, n: int = 20, sheet: str = "",
                       user_id: str = "", conversation_id: str = "") -> str:
    """Frequency of each distinct value in a column (most common first).
    user_id/conversation_id are filled in automatically."""
    df, error = await _load(user_id, conversation_id, file_name, sheet)
    if df is None:
        return error
    if error := _check_columns(df, column):
        return error
    counts = df[column].value_counts().head(max(1, min(n, MAX_ROWS_OUT))).reset_index()
    counts.columns = [column, "count"]
    return _table(counts)


@mcp.tool()
async def correlation(file_name: str, sheet: str = "", user_id: str = "", conversation_id: str = "") -> str:
    """Pearson correlation matrix of the numeric columns. user_id/conversation_id are filled in automatically."""
    df, error = await _load(user_id, conversation_id, file_name, sheet)
    if df is None:
        return error
    numeric = df.select_dtypes("number")
    if numeric.shape[1] < 2:
        return "Need at least two numeric columns for a correlation."
    return truncate(numeric.corr().round(3).to_markdown())


if __name__ == "__main__":
    mcp.run()
