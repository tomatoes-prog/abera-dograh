"""Offline document processing, run in a bounded subprocess by the ARQ worker.

No credentials, model calls, remote URLs, or user-supplied executables are used
here. Embeddings are a separate operation using the organization's provider.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx", ".doc", ".txt", ".md", ".json"})
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 2_000_000
MAX_PDF_PAGES = 200
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
PROCESSING_TIMEOUT_SECONDS = 180


def _run_tool(args: list[str], *, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ValueError(
            "El lector de documentos no está instalado. Usa la imagen de Abera "
            "o instala Poppler, Tesseract y antiword."
        ) from exc
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        # Tool stderr can include source text and paths; do not expose it.
        raise ValueError(
            "No se pudo leer el documento dentro del tiempo permitido."
        ) from exc
    return result.stdout.decode("utf-8", errors="strict")


def _pdf_text(path: Path) -> tuple[str, dict]:
    from pypdf import PdfReader

    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("El PDF tiene contraseña. Sube una copia sin contraseña.")
    if len(reader.pages) > MAX_PDF_PAGES:
        raise ValueError(f"El PDF supera el límite de {MAX_PDF_PAGES} páginas.")
    pages: list[str] = []
    ocr_pages: list[int] = []
    length = 0
    with tempfile.TemporaryDirectory(prefix="abera-ocr-") as temp_dir:
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text(extraction_mode="layout") or ""
            if len(text.strip()) < 20:
                image_prefix = str(Path(temp_dir) / "page")
                _run_tool(
                    [
                        "pdftoppm",
                        "-f",
                        str(index),
                        "-l",
                        str(index),
                        "-scale-to",
                        "1600",
                        "-singlefile",
                        "-png",
                        str(path),
                        image_prefix,
                    ]
                )
                recognized = _run_tool(
                    [
                        "tesseract",
                        image_prefix + ".png",
                        "stdout",
                        "-l",
                        "spa+eng",
                    ]
                )
                Path(image_prefix + ".png").unlink(missing_ok=True)
                if recognized.strip():
                    text = recognized
                    ocr_pages.append(index)
            length += len(text)
            if length > MAX_EXTRACTED_CHARACTERS:
                raise ValueError(
                    "El documento contiene demasiado texto para procesarlo."
                )
            pages.append(text.strip())
    return "\n\n".join(pages), {"page_count": len(pages), "ocr_pages": ocr_pages}


def _docx_text(path: Path) -> str:
    from docx import Document
    from docx.table import Table

    # A small compressed upload can expand into an unbounded XML document.
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if (
            len(entries) > 2000
            or sum(entry.file_size for entry in entries) > MAX_ARCHIVE_BYTES
        ):
            raise ValueError("El Word supera el tamaño permitido al descomprimirlo.")
    document = Document(path)
    blocks: list[str] = []
    for item in document.iter_inner_content():
        if isinstance(item, Table):
            blocks.extend(
                " | ".join(cell.text for cell in row.cells) for row in item.rows
            )
        else:
            text = item.text
            style = item.style.name if item.style else ""
            if style.startswith("Heading ") and style[-1:].isdigit():
                text = "#" * min(int(style[-1]), 6) + " " + text
            blocks.append(text)
    return "\n\n".join(blocks)


def extract_document(path: Path, filename: str) -> tuple[str, dict]:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise ValueError("Formato no admitido. Usa PDF, Word, TXT, Markdown o JSON.")
    if not path.is_file() or path.stat().st_size > MAX_FILE_SIZE_BYTES:
        raise ValueError("El archivo no existe o supera el límite de 5 MB.")
    metadata: dict = {"processor": "abera-local", "source_format": extension}
    if extension == ".pdf":
        text, pdf_metadata = _pdf_text(path)
        metadata.update(pdf_metadata)
    elif extension == ".docx":
        text = _docx_text(path)
    elif extension == ".doc":
        text = _run_tool(["antiword", "-m", "UTF-8", str(path)])
    else:
        raw = path.read_bytes()
        # Accept UTF-16 exported by Windows as well as UTF-8 with an optional BOM.
        encoding = (
            "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        )
        text = raw.decode(encoding)
        if extension == ".json":
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    if len(text) > MAX_EXTRACTED_CHARACTERS:
        raise ValueError("El documento contiene demasiado texto para procesarlo.")
    if not text.strip():
        raise ValueError("No se encontró texto legible en el documento.")
    return text, metadata


def chunk_document(text: str, filename: str, max_tokens: int) -> list[dict]:
    import tiktoken

    if not 16 <= max_tokens <= 4096:
        raise ValueError("El tamaño del fragmento debe estar entre 16 y 4096 tokens.")
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text, disallowed_special=())
    chunks: list[dict] = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        # A token boundary may bisect a UTF-8 code point (Spanish, emoji, etc.).
        # Adjust the boundary rather than inserting replacement characters.
        while end > start:
            try:
                chunk_text = encoding.decode(tokens[start:end], errors="strict")
                break
            except UnicodeDecodeError:
                end -= 1
        if end == start:
            raise ValueError("No se pudo dividir el texto sin perder caracteres.")
        chunks.append(
            {
                "chunk_text": chunk_text,
                "contextualized_text": f"Documento: {Path(filename).name}\n{chunk_text}",
                "chunk_index": len(chunks),
                "chunk_metadata": {
                    "source": Path(filename).name,
                    "processor": "abera-local",
                },
                "token_count": end - start,
            }
        )
        start = end
    return chunks


def process_document(
    path: Path, filename: str, retrieval_mode: str, max_tokens: int
) -> dict:
    if retrieval_mode not in {"chunked", "full_document"}:
        raise ValueError("Elige búsqueda por fragmentos o documento completo.")
    text, metadata = extract_document(path, filename)
    result = {"full_text": text, "chunks": [], "docling_metadata": metadata}
    if retrieval_mode == "chunked":
        result["chunks"] = chunk_document(text, filename, max_tokens)
    return result


async def process_document_locally(
    *,
    file_path: str,
    filename: str,
    retrieval_mode: str,
    max_tokens: int,
) -> dict:
    # The parser inherits no AWS/provider/database secrets from the ARQ worker.
    child_env = {
        key: value
        for key, value in os.environ.items()
        if key
        in {
            "PATH",
            "PYTHONPATH",
            "VIRTUAL_ENV",
            "LANG",
            "LC_ALL",
            "SYSTEMROOT",
            "TIKTOKEN_CACHE_DIR",
        }
    }
    child_env["OMP_THREAD_LIMIT"] = "1"
    child_env["RAYON_NUM_THREADS"] = "1"
    child_env["PYTHONUNBUFFERED"] = "1"
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "api.services.knowledge_base.processing",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=child_env,
        start_new_session=(os.name == "posix"),
    )
    payload = json.dumps(
        {
            "file_path": file_path,
            "filename": filename,
            "retrieval_mode": retrieval_mode,
            "max_tokens": max_tokens,
        }
    ).encode()
    try:
        output, _stderr = await asyncio.wait_for(
            process.communicate(payload),
            timeout=PROCESSING_TIMEOUT_SECONDS,
        )
    except BaseException:
        if process.returncode is None:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            await process.wait()
        raise
    if not output or process.returncode not in {0, 1}:
        raise ValueError(
            "El lector alcanzó el límite de recursos o no pudo procesar el archivo."
        )
    result = json.loads(output)
    if process.returncode != 0:
        raise ValueError(result.get("error", "No se pudo procesar el documento."))
    return result


async def process_document_in_queue(*, redis, **arguments) -> dict:
    """Run at most one reader per runtime, including across ARQ replicas.

    Busy jobs return to ARQ instead of occupying workers or starting more OCR
    processes. The lease outlives the hard subprocess timeout and also expires
    if a worker dies. This controls document CPU separately from call slots.
    """
    import secrets

    from arq import Retry

    lock_key = "dograh:knowledge_base:parser"
    token = secrets.token_hex(16)
    if not await redis.set(
        lock_key, token, nx=True, ex=PROCESSING_TIMEOUT_SECONDS + 60
    ):
        raise Retry(defer=15)
    try:
        return await process_document_locally(**arguments)
    finally:
        await redis.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            lock_key,
            token,
        )


def _main() -> None:
    if os.name == "posix":
        import resource

        # Only the parser child is limited. API and live calls are unaffected.
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (60, 65))
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024,) * 2)
        os.nice(10)
    try:
        request = json.loads(sys.stdin.buffer.read(16 * 1024))
        result = process_document(
            Path(request["file_path"]),
            request["filename"],
            request["retrieval_mode"],
            request["max_tokens"],
        )
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        message = (
            str(exc)
            if isinstance(exc, ValueError)
            else "No se pudo leer el documento. Revisa su formato."
        )
        print(json.dumps({"error": message}, ensure_ascii=False))
        raise SystemExit(1)


if __name__ == "__main__":
    _main()
