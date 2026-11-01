
from langchain_text_splitters import RecursiveCharacterTextSplitter


def chunk_document(document_text: str) -> list[str]:
    """Split document text into temporary chunks."""

    if not document_text or not document_text.strip():
        raise ValueError("Document text is empty.")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""]
    )

    return text_splitter.split_text(document_text)


if __name__ == "__main__":
    from pathlib import Path

    input_path = Path("extracted_text.txt")

    if not input_path.exists():
        raise FileNotFoundError(
            "extracted_text.txt not found. Run read_pdf.py first."
        )

    document_text = input_path.read_text(encoding="utf-8")
    chunks = chunk_document(document_text)

    print("Temporary chunking completed!")
    print("Total chunks:", len(chunks))

    for index, chunk in enumerate(chunks[:3], start=1):
        print(f"\n--- Chunk {index} ---")
        print(chunk)
