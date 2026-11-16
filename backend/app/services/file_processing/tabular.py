"""Robust tabular file reading shared by ingestion (RAG) and agent tools."""

import pandas as pd


def _leading_comment_lines(path: str, max_scan: int = 50) -> int:
    """Count leading lines that start with '#' (common in exported/sample CSVs)."""
    count = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if count >= max_scan or not line.lstrip().startswith("#"):
                break
            count += 1
    return count


def read_csv_robust(path: str, **kwargs) -> pd.DataFrame:
    """
    pd.read_csv treats the first line as the header. If a file starts with
    "# comment" lines, the comment becomes the only column name and every real
    column is lost. Skip those lines first. (comment="#" is NOT used because it
    would also cut values that legitimately contain '#'.)
    """
    return pd.read_csv(path, skiprows=_leading_comment_lines(path), **kwargs)
