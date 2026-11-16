import os
import re
import zipfile
from typing import Any
import re
from uuid import uuid4
from typing import List, Dict
import pymupdf4llm
from langchain_text_splitters import RecursiveCharacterTextSplitter
import pandas as pd
from app.services.file_processing.tabular import read_csv_robust
from docx import Document
from fastapi import HTTPException
from app.services.vision.vision_service import transcribe_image
from app.services.file_processing.file_chunkers import *
from app.services.file_processing.file_chunkers import chunk_sections

MAX_OFFICE_UNCOMPRESSED_BYTES = 50 * 1024 * 1024


def validate_office_archive(file_path: str) -> None:
    with zipfile.ZipFile(file_path) as archive:
        total_uncompressed_size = sum(file_info.file_size for file_info in archive.infolist())

    if total_uncompressed_size > MAX_OFFICE_UNCOMPRESSED_BYTES:
        raise HTTPException(status_code=400, detail="Office file is too large to process safely")

MAX_SCANNED_PDF_PAGES = 10  # vision calls per scanned PDF (free-tier protection)


def pdf_to_markdown(file_path: str) -> str:
    """
    Text PDFs: pymupdf4llm with OCR disabled (its default silently runs local Tesseract).
    Scanned PDFs (no text layer): render pages to PNG and transcribe with Gemini vision.
    """
    text = pymupdf4llm.to_markdown(file_path, use_ocr=False)
    if len(text.strip()) >= 50:
        return text

    import os
    import tempfile
    import fitz

    pages = []
    with fitz.open(file_path) as doc, tempfile.TemporaryDirectory() as tmp:
        for index, page in enumerate(doc):
            if index >= MAX_SCANNED_PDF_PAGES:
                pages.append(f"[Only the first {MAX_SCANNED_PDF_PAGES} scanned pages were transcribed.]")
                break
            image_path = os.path.join(tmp, f"page-{index + 1}.png")
            page.get_pixmap(dpi=150).save(image_path)
            pages.append(f"# Page {index + 1}\n{transcribe_image(image_path)}")
    return "\n\n".join(pages)


def parse_pdf(file_path: str) -> List[Dict]:
    pdf_txt=pdf_to_markdown(file_path)
    lines = pdf_txt.split("\n")
    sections = []
    current_section = {
        "title": "UNKNOWN",
        "section_id": str(uuid4()),
        "content": []
    }

    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if re.match(r"^#{1,3}\s+", line):
            if current_section["content"]:
                sections.append(current_section)
            title = re.sub(r"^#{1,3}\s+", "", line).strip()
            current_section = {
                "title": title,
                "section_id": str(uuid4()),
                "content": []
            }

        else:
            current_section["content"].append(line)

    if current_section["content"]:
        sections.append(current_section)

    return sections
    # with open(file_path, "rb") as f:
    #     reader = PyPDF2.PdfReader(f)
    #     content= "\n".join([page.extract_text() or "" for page in reader.pages])
    #     chunks=chunk_pdf(content)
    #     return chunks

def is_title_line(line: str) -> bool:
    if len(line.split()) <= 6:
        if line.istitle() or line.isupper():
            return True

    if re.match(r"^[A-Z][A-Za-z\s]+$", line) and len(line) < 60:
        return True

    return False


def fallback_detect_sections(md_text: str) -> List[Dict]:
    lines = md_text.split("\n")

    sections = []
    current_section = {
        "title": "UNKNOWN",
        "section_id": str(uuid4()),
        "content": []
    }

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if is_title_line(line):
            if current_section["content"]:
                sections.append(current_section)

            current_section = {
                "title": line,
                "section_id": str(uuid4()),
                "content": []
            }
        else:
            current_section["content"].append(line)

    if current_section["content"]:
        sections.append(current_section)

    return sections
def process_pdf(file_path: str) -> List[Dict]:
    sections = parse_pdf(file_path)

    # if len(sections) <= 1:
    #     sections = fallback_detect_sections(md_text)

    chunks = chunk_sections(sections)

    return chunks

def process_markdown(file_path: str) -> list[str]:
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join([line.rstrip() for line in text.split("\n")])
    text = text.strip()
    chunks=chunk_markdown_and_docx(text)
    return chunks

def process_docx(file_path: str) -> list[str]:
    validate_office_archive(file_path)
    doc = Document(file_path)
    structured_text = []
    for para in doc.paragraphs:
        style_name = None
        try:
            style_name = getattr(para.style, "name", None)
        except Exception:
            style_name = None

        if style_name and style_name.startswith("Heading"):
            level_str = style_name.replace("Heading ", "")
            try:
                level = int(level_str)
                structured_text.append(f"\n{'#' * level} {para.text}\n")
            except ValueError:
                structured_text.append(f"\n# {para.text}\n")
        else:
            structured_text.append(para.text)
    content_str = "\n".join(structured_text)
    chunks = chunk_markdown_and_docx(content_str)
    return chunks

def process_text(file_path: str) -> list[str]:
    with open(file_path, "r", encoding="utf-8") as f:
        text= f.read()
    chunks=chunk_txt(text)
    return chunks

def process_image(file_path: str) -> list[str]:
    # Gemini vision instead of local Tesseract OCR: reads text AND describes charts/photos.
    img_text = transcribe_image(file_path)
    if not img_text:
        return []
    chunks=recursive_character_chunking_for_images(img_text)
    return chunks

def process_code(file_path: str) -> list[dict[str, Any]]:
    with open(file_path, "r", encoding="utf-8") as f:
        file_content = f.read()
    filename = os.path.basename(file_path)
    chunks = chunk_code_ast(file_content, filename)
    return chunks

def process_csv(file_path: str) -> list[dict[str, Any]]:
    df = read_csv_robust(file_path)
    chunks=chunk_dataframe(df, file_path)
    return chunks

def process_xlsx(file_path: str) -> list[dict[str, Any]]:
    validate_office_archive(file_path)
    chunks=chunk_xlsx(file_path)
    return chunks
