
import hashlib
import sqlite3
from pathlib import Path
from io import BytesIO

from bs4 import BeautifulSoup
from pypdf import PdfReader


# --------------------------------------------------
# 1. Permanent document storage
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DOCUMENTS_DIR = BASE_DIR / "documents"
DATABASE_PATH = BASE_DIR / "document_history.db"

DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# 2. Database connection
# --------------------------------------------------

def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_history():
    """Create the history table without deleting existing records."""

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                policy_type TEXT NOT NULL,
                source_url TEXT NOT NULL,
                file_path TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                last_checked TEXT NOT NULL,
                UNIQUE(company, policy_type, source_url, content_hash)
            )
        """)


# --------------------------------------------------
# 3. Find a saved document
# --------------------------------------------------


def find_saved_document(company: str, policy_type: str):
    """Quickly find the latest saved document."""

    initialize_history()

    with get_connection() as connection:
        return connection.execute("""
            SELECT *
            FROM documents
            WHERE company = ? COLLATE NOCASE
              AND policy_type = ? COLLATE NOCASE
            ORDER BY last_checked DESC, id DESC
            LIMIT 1
        """, (
            company.strip(),
            policy_type.strip(),
        )).fetchone()



# --------------------------------------------------
# 4. Content hash
# --------------------------------------------------

def calculate_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# --------------------------------------------------
# 5. Save the original document
# --------------------------------------------------

def save_original_document(
    company: str,
    policy_type: str,
    source_url: str,
    content: bytes,
    filename: str,
    last_checked: str,
) -> dict:
    """Save original PDF/HTML bytes and register them in SQLite."""

    initialize_history()

    if not company.strip() or not policy_type.strip():
        raise ValueError("Company and policy type are required.")

    if not source_url.strip():
        raise ValueError("Source URL is required.")

    if not content:
        raise ValueError("Document content is empty.")

    safe_name = Path(filename).name or "policy_document.txt"

    safe_company = "".join(
        char if char.isalnum() or char in "-_" else "_"
        for char in company.strip()
    )[:80] or "company"

    company_dir = DOCUMENTS_DIR / safe_company
    company_dir.mkdir(parents=True, exist_ok=True)

    digest = calculate_content_hash(content)
    destination = company_dir / f"{digest[:16]}_{safe_name}"

    # Preserve the original bytes.
    if not destination.exists():
        destination.write_bytes(content)

    with get_connection() as connection:
        connection.execute("""
            INSERT OR IGNORE INTO documents (
                company,
                policy_type,
                source_url,
                file_path,
                content_hash,
                last_checked
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            company.strip(),
            policy_type.strip(),
            source_url.strip(),
            str(destination.resolve()),
            digest,
            last_checked,
        ))

    return {
        "company": company.strip(),
        "policy_type": policy_type.strip(),
        "source_url": source_url.strip(),
        "file_path": str(destination.resolve()),
        "content_hash": digest,
        "last_checked": last_checked,
    }


# --------------------------------------------------
# 6. Extract readable text from a saved document
# --------------------------------------------------

def load_saved_document(record) -> str | None:
    """Extract readable text without sending HTML tags to RAG."""

    if record is None:
        return None

    try:
        file_path = Path(record["file_path"]).resolve()
        file_path.relative_to(DOCUMENTS_DIR.resolve())
    except (ValueError, OSError, TypeError):
        print("Invalid document path.")
        return None

    if not file_path.is_file():
        print("Saved original document was not found.")
        return None

    try:
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            reader = PdfReader(str(file_path))
            text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            )

        elif suffix in {".html", ".htm"}:
            raw_html = file_path.read_bytes()

            soup = BeautifulSoup(
                raw_html,
                "html.parser",
            )

            # Remove elements that usually do not contain policy text.
            for element in soup([
                "script",
                "style",
                "nav",
                "footer",
                "header",
                "noscript",
            ]):
                element.decompose()

            text = soup.get_text(
                separator="\n",
                strip=True,
            )

        elif suffix in {".txt", ".md"}:
            text = file_path.read_text(encoding="utf-8")

        else:
            print(f"Unsupported saved file type: {suffix}")
            return None

        text = text.strip()

        if len(text) < 100:
            print("Saved document contains too little readable text.")
            return None

        return text

    except Exception as exc:
        print("Could not read saved document:", exc)
        return None


# --------------------------------------------------
# 7. Standalone initialization test
# --------------------------------------------------

if __name__ == "__main__":
    initialize_history()

    print("Document history initialized successfully.")
    print("Database:", DATABASE_PATH)
    print("Original documents folder:", DOCUMENTS_DIR)
