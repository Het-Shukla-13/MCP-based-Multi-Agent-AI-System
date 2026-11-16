// Mirrors backend/app/services/file_processing/file_type_config.py. The SERVER is the
// real gatekeeper (it checks magic bytes too); this only gives instant feedback.
export const MAX_UPLOAD_BYTES = 7 * 1024 * 1024;
export const ALLOWED_EXTENSIONS = [
  "pdf", "docx", "txt", "md", "json", "csv", "xlsx",
  "jpg", "jpeg", "png",
  "py", "js", "ts", "java", "c", "cpp", "go",
];
export const ACCEPT_ATTRIBUTE = ALLOWED_EXTENSIONS.map((ext) => `.${ext}`).join(",");

/** Split files into accepted and rejected (with a reason each). */
export function checkFiles(files) {
  const accepted = [];
  const rejected = [];
  for (const file of files) {
    const ext = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "";
    if (!ALLOWED_EXTENSIONS.includes(ext)) rejected.push({ name: file.name, reason: "unsupported type" });
    else if (file.size === 0) rejected.push({ name: file.name, reason: "empty file" });
    else if (file.size > MAX_UPLOAD_BYTES) rejected.push({ name: file.name, reason: "larger than 7 MB" });
    else accepted.push(file);
  }
  return { accepted, rejected };
}
