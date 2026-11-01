
from pathlib import Path
from pypdf import PdfReader

# 1. Define the PDF file location
pdf_path = Path("data/sample.pdf")

# 2. Check whether the PDF exists
if not pdf_path.exists():
    raise FileNotFoundError(
        f"PDF not found: {pdf_path.resolve()}"
    )

# 3. Open and read the PDF
reader = PdfReader(str(pdf_path))

print("PDF opened successfully!")
print("Total pages:", len(reader.pages))

# 4. Extract text from every page
all_text = []

for page_number, page in enumerate(reader.pages, start=1):
    text = page.extract_text() or ""

    print(f"Extracting page {page_number}...")

    if text.strip():
        all_text.append(
            f"\n--- Page {page_number} ---\n{text}"
        )

# 5. Combine all extracted text
document_text = "\n".join(all_text)

# 6. Check whether any text was extracted
if not document_text.strip():
    raise ValueError(
        "No text extracted. This may be a scanned PDF."
    )

# 7. Save the extracted text to a file
output_path = Path("extracted_text.txt")
output_path.write_text(document_text, encoding="utf-8")

# 8. Display the results
print("\nText extraction completed!")
print("Characters extracted:", len(document_text))
print("Saved to:", output_path.resolve())

print("\nFirst 1000 characters:\n")
print(document_text[:1000])
