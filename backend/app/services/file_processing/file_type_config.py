"""Single source of truth for which uploads are accepted and how they are parsed."""

MAX_UPLOAD_BYTES = 7 * 1024 * 1024  # 7 MB (assignment requirement)

TEXT_FILE_EXTENSIONS = {".txt", ".json"}
MARKDOWN_FILE_EXTENSIONS = {".md"}
CODE_FILE_EXTENSIONS = {".py", ".js", ".ts", ".java", ".cpp", ".c", ".go"}
IMAGE_FILE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
DOCUMENT_FILE_EXTENSIONS = {".pdf", ".docx"}
DATA_FILE_EXTENSIONS = {".csv", ".xlsx"}

# Derived, so a new parser can never be "supported but rejected at upload" again.
ALLOWED_FILE_EXTENSIONS = {
    ext.lstrip(".")
    for group in (
        TEXT_FILE_EXTENSIONS,
        MARKDOWN_FILE_EXTENSIONS,
        CODE_FILE_EXTENSIONS,
        IMAGE_FILE_EXTENSIONS,
        DOCUMENT_FILE_EXTENSIONS,
        DATA_FILE_EXTENSIONS,
    )
    for ext in group
}

# Text-like formats: must decode as UTF-8 and contain no NUL bytes.
TEXT_LIKE_EXTENSIONS = {
    ext.lstrip(".")
    for ext in TEXT_FILE_EXTENSIONS | MARKDOWN_FILE_EXTENSIONS | CODE_FILE_EXTENSIONS | {".csv"}
}

# MIME type we store, based on the verified content (never the client's claim).
MIME_BY_EXTENSION = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "csv": "text/csv",
    "json": "application/json",
    "md": "text/markdown",
    "txt": "text/plain",
    "py": "text/x-python",
    "js": "text/javascript",
    "ts": "text/x-typescript",
    "java": "text/x-java",
    "c": "text/x-c",
    "cpp": "text/x-c++",
    "go": "text/x-go",
}
