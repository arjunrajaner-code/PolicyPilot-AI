
from io import BytesIO
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


def load_document(url: str) -> dict:
    """Fetch a public webpage or PDF and extract its text."""

    parsed = urlparse(url)

    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only valid HTTPS document URLs are accepted.")

    response = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "CompanyPolicyResearchBot/1.0"},
    )
    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type", ""
    ).lower()

    if "application/pdf" in content_type or url.lower().endswith(".pdf"):
        reader = PdfReader(BytesIO(response.content))
        text = "\n".join(
            page.extract_text() or "" for page in reader.pages
        )
        title = url.rsplit("/", 1)[-1]

    elif "text/html" in content_type:
        soup = BeautifulSoup(response.text, "html.parser")

        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        title = soup.title.get_text(" ", strip=True) if soup.title else url
        text = soup.get_text(separator="\n", strip=True)

    else:
        raise ValueError(
            f"Unsupported document type: {content_type}"
        )

    if len(text.strip()) < 100:
        raise ValueError(
            "Not enough readable text was extracted from this URL."
        )

    return {
        "title": title,
        "url": url,
        "text": text.strip(),
        "content_type": content_type,
    }


if __name__ == "__main__":
    url = input("Paste a public webpage or PDF URL: ").strip()

    try:
        document = load_document(url)

        print("\nDocument loaded successfully!")
        print("Title:", document["title"])
        print("URL:", document["url"])
        print("Characters extracted:", len(document["text"]))
        print("\nText preview:\n")
        print(document["text"][:1000])

    except Exception as exc:
        print("Document loading failed:", exc)
