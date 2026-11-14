from pathlib import Path

from .schema import PaperChunk, PdfRegion


def chunk_pdf(path: Path) -> list[PaperChunk]:
    try:
        from docling.chunking import HybridChunker
        from docling.document_converter import DocumentConverter
        from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Install PDF support with uv sync --locked --extra pdf"
        ) from exc

    import tiktoken

    document = DocumentConverter().convert(path, max_num_pages=300).document
    chunker = HybridChunker(
        tokenizer=OpenAITokenizer(
            tokenizer=tiktoken.get_encoding("cl100k_base"), max_tokens=512
        )
    )
    chunks = []
    for chunk in chunker.chunk(document):
        text = chunker.contextualize(chunk).strip()
        if text:
            regions = []
            for item in chunk.meta.doc_items:
                for prov in item.prov:
                    size = document.pages[prov.page_no].size
                    bbox = prov.bbox.to_top_left_origin(size.height)
                    regions.append(
                        PdfRegion(
                            page=prov.page_no,
                            left=bbox.l / size.width,
                            top=bbox.t / size.height,
                            right=bbox.r / size.width,
                            bottom=bbox.b / size.height,
                        )
                    )
            chunks.append(
                PaperChunk(
                    number=len(chunks) + 1,
                    text=text,
                    headings=chunk.meta.headings or [],
                    pages=sorted({region.page for region in regions}),
                    regions=regions,
                )
            )
    if not chunks:
        raise ValueError("Docling could not extract any searchable text from the PDF")
    return chunks


def first_page_text(path: Path) -> str:
    from pypdfium2 import PdfDocument

    with PdfDocument(path) as document:
        return document[0].get_textpage().get_text_range()[:16000]
