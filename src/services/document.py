from io import BytesIO

from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader


def extract_pages(filename: str, content: bytes) -> list[tuple[int, str]]:
    suffix = filename.lower().rsplit(".", 1)[-1]

    if suffix == "txt":
        try:
            return [(1, content.decode("utf-8-sig"))]
        except UnicodeDecodeError as exc:
            raise ValueError("TXT file must be UTF-8 encoded") from exc

    if suffix != "pdf":
        raise ValueError("Only PDF and TXT files are supported")

    try:
        reader = PdfReader(BytesIO(content))
        return [
            (page_number, page.extract_text() or "")
            for page_number, page in enumerate(reader.pages, start=1)
        ]
    except Exception as exc:
        raise ValueError("Could not read this PDF") from exc


def chunk_pages(
    pages: list[tuple[int, str]],
    tokenizer,
    strategy: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[dict]:
    chunks = []

    for page_number, text in pages:
        if not text.strip():
            continue

        if strategy == "fixed":
            token_ids = tokenizer.encode(text, add_special_tokens=False)
            step = chunk_size - chunk_overlap

            for start in range(0, len(token_ids), step):
                part = token_ids[start : start + chunk_size]
                chunk_text = tokenizer.decode(
                    part,
                    skip_special_tokens=True,
                ).strip()

                if chunk_text:
                    chunks.append({
                        "text": chunk_text,
                        "page_number": page_number,
                    })

                if start + chunk_size >= len(token_ids):
                    break
        else:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                length_function=lambda value: len(
                    tokenizer.encode(value, add_special_tokens=False)
                ),
                separators=["\n\n", "\n", ". ", " ", ""],
            )

            for chunk_text in splitter.split_text(text):
                if chunk_text.strip():
                    chunks.append({
                        "text": chunk_text.strip(),
                        "page_number": page_number,
                    })

    return chunks