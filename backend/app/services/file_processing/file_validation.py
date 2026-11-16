"""
Content sniffing: check that an uploaded file's bytes match its extension.

The filename and the browser's Content-Type header are both chosen by the client,
so neither can be trusted. Most binary formats start with fixed "magic bytes"
(a file signature); text formats must at least decode as UTF-8.
No external tools or models: pure Python checks.
"""

import zipfile

from app.services.file_processing.file_type_config import TEXT_LIKE_EXTENSIONS

MAGIC_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF-",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpg": (b"\xff\xd8\xff",),
    "jpeg": (b"\xff\xd8\xff",),
    # docx/xlsx are ZIP archives (Office Open XML); checked further below.
    "docx": (b"PK\x03\x04",),
    "xlsx": (b"PK\x03\x04",),
}

# The part every valid Office Open XML file of that kind must contain.
OFFICE_REQUIRED_PART = {
    "docx": "word/document.xml",
    "xlsx": "xl/workbook.xml",
}


def _looks_like_utf8_text(head: bytes) -> bool:
    if b"\x00" in head:  # NUL bytes mean binary data
        return False
    try:
        head.decode("utf-8")
        return True
    except UnicodeDecodeError as exc:
        # The 8 KB sample may cut a multi-byte character in half at the very end.
        return exc.start >= len(head) - 3


def sniff_matches_extension(file_path: str, ext: str, head: bytes) -> tuple[bool, str]:
    """Return (ok, reason). `head` is the first few KB of the file."""
    ext = ext.lower()

    signatures = MAGIC_SIGNATURES.get(ext)
    if signatures is not None:
        if not head.startswith(signatures):
            return False, f"content is not a valid .{ext} file"
        required_part = OFFICE_REQUIRED_PART.get(ext)
        if required_part:
            try:
                with zipfile.ZipFile(file_path) as archive:
                    if required_part not in archive.namelist():
                        return False, f"archive is not a valid .{ext} document"
            except zipfile.BadZipFile:
                return False, f"corrupted .{ext} file"
        return True, ""

    if ext in TEXT_LIKE_EXTENSIONS:
        if not _looks_like_utf8_text(head):
            return False, f".{ext} files must be UTF-8 text"
        return True, ""

    return False, f"no content check defined for .{ext}"
