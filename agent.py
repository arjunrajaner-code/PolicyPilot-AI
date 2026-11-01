
import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from groq import Groq

from web_search import (
    search_company_policy,
    get_known_domains,
    is_official_domain,
)
from document_loader import load_document
from document_history import (
    initialize_history,
    find_saved_document,
    load_saved_document,
    save_original_document,
)
from rag_chat import ask_question


# --------------------------------------------------
# 1. Groq configuration
# --------------------------------------------------

load_dotenv()

QUERY_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-20b",
)

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError(
        "GROQ_API_KEY is missing. Add it to your .env file."
    )

client = Groq(
    api_key=api_key,
    timeout=30.0,
    max_retries=1,
)


# --------------------------------------------------
# 2. Understand natural-language user questions
# --------------------------------------------------

def understand_user_query(user_prompt: str) -> dict:
    """Extract the company and policy topic using Groq."""

    if not user_prompt or not user_prompt.strip():
        raise ValueError("Please enter a question.")

    print("Understanding your question with Groq...")

    start_time = time.perf_counter()

    response = client.chat.completions.create(
        model=QUERY_MODEL,
        messages=[
            {
                "role": "system",
                "content": """
You are a company-policy query understanding assistant.

Understand questions regardless of tone, emotion, slang,
grammar mistakes, spelling mistakes, emojis, or wording.

The user may use formal English, casual English, or Tanglish.
Infer the intended company and policy topic from the full message.
Do not rely on fixed example sentences or exact keyword matches.

Return a valid JSON object with exactly these fields:
{
  "company": "company name",
  "policy_type": "short normalized policy topic",
  "is_company_policy_question": true
}

Rules:
- Extract the company only when reasonably identifiable.
- Normalize the topic into concise English.
- Do not invent a company or policy intent.
- If the company is missing or the question is not about
  company policy, set is_company_policy_question to false.
- Do not answer the policy question.
- Return JSON only.
""",
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=200,
    )

    print(
        f"Query understanding completed in "
        f"{time.perf_counter() - start_time:.2f} seconds."
    )

    try:
        content = response.choices[0].message.content

        if not content:
            raise ValueError("Groq returned an empty response.")

        result = json.loads(content)

        company = result.get("company")
        policy_type = result.get("policy_type")
        is_policy_question = result.get(
            "is_company_policy_question", False
        )

        if (
            is_policy_question is not True
            or not isinstance(company, str)
            or not company.strip()
            or not isinstance(policy_type, str)
            or not policy_type.strip()
        ):
            raise ValueError(
                "Please mention the company and ask about its policy."
            )

        return {
            "company": company.strip(),
            "policy_type": policy_type.strip(),
        }

    except (json.JSONDecodeError, TypeError, KeyError) as exc:
        raise ValueError(
            "Could not understand the question. Please rephrase it."
        ) from exc


# --------------------------------------------------
# 3. Basic policy relevance check
# --------------------------------------------------

def policy_content_is_relevant(
    title: str,
    text: str,
    policy_type: str,
) -> bool:
    """First-pass relevance check, not proof of authenticity."""

    title_text = title.lower()
    content = text.lower()
    policy = policy_type.lower().strip()

    if len(text.strip()) < 300:
        return False

    topic_groups = {
        "leave": [
            "leave", "paid time off", "pto", "sick leave",
            "annual leave", "parental leave", "vacation",
            "time off", "absence",
        ],
        "salary": [
            "salary", "pay", "paid", "unpaid", "wages",
            "compensation", "payroll",
        ],
        "holiday": [
            "holiday", "public holiday", "paid holiday",
            "company holidays",
        ],
        "work from home": [
            "work from home", "remote work", "hybrid",
            "remote working",
        ],
    }

    matched_topics = []

    for group, terms in topic_groups.items():
        if group in policy or any(term in policy for term in terms):
            matched_topics.extend(terms)

    if not matched_topics:
        matched_topics = [policy]

    title_match = any(term in title_text for term in matched_topics)
    content_match = any(term in content for term in matched_topics)

    return title_match or content_match


# --------------------------------------------------
# 4. Safe filename
# --------------------------------------------------

def get_filename(title: str, content_type: str, url: str) -> str:
    path_name = Path(urlparse(url).path).name

    if path_name and "." in path_name:
        return Path(path_name).name

    safe_title = "".join(
        char if char.isalnum() or char in "-_" else "_"
        for char in title
    )[:80] or "policy_document"

    if "pdf" in content_type.lower():
        return safe_title + ".pdf"

    return safe_title + ".html"


# --------------------------------------------------
# 5. Download original document
# --------------------------------------------------

def download_original(
    url: str,
    allowed_domains: list[str],
) -> tuple[bytes, str]:

    parsed = urlparse(url)

    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Only HTTPS URLs are allowed.")

    if not is_official_domain(url, allowed_domains):
        raise ValueError("URL is not an approved company domain.")

    response = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "CompanyPolicyAssistant/1.0"},
        allow_redirects=False,
    )

    if 300 <= response.status_code < 400:
        raise ValueError(
            "The page redirects. Verify its destination first."
        )

    response.raise_for_status()

    content_type = response.headers.get(
        "Content-Type", ""
    ).lower()

    if (
        "application/pdf" not in content_type
        and "text/html" not in content_type
    ):
        raise ValueError(
            f"Unsupported document type: {content_type}"
        )

    return response.content, content_type


# --------------------------------------------------
# 6. Document freshness
# --------------------------------------------------

def is_document_fresh(record, max_age_days: int = 7) -> bool:

    if record is None:
        return False

    try:
        last_checked = datetime.fromisoformat(
            record["last_checked"]
        )

        if last_checked.tzinfo is None:
            last_checked = last_checked.replace(
                tzinfo=timezone.utc
            )

        age = datetime.now(timezone.utc) - last_checked.astimezone(
            timezone.utc
        )

        return timedelta(0) <= age <= timedelta(days=max_age_days)

    except (ValueError, TypeError, KeyError):
        return False


# --------------------------------------------------
# 7. Main company-policy agent
# --------------------------------------------------

def run_agent(
    company: str,
    policy_type: str,
    original_question: str,
) -> None:

    company = company.strip()
    policy_type = policy_type.strip()

    if not company or not policy_type:
        print("Company and policy topic are required.")
        return

    initialize_history()

    print(f"\nCompany detected: {company}")
    print(f"Policy topic detected: {policy_type}")

    allowed_domains = get_known_domains(company)

    if not allowed_domains:
        print(
            f"\nNo approved official domain is configured for {company}."
        )
        print(
            "Verify the company's official domain and add it to "
            "web_search.py before searching its documents."
        )
        return

    # A. Check document history first.
    start_time = time.perf_counter()
    saved_record = find_saved_document(company, policy_type)

    print(
        f"Document history lookup: "
        f"{time.perf_counter() - start_time:.2f} seconds"
    )

    if saved_record and is_document_fresh(saved_record):
        saved_url = saved_record["source_url"]

        if is_official_domain(saved_url, allowed_domains):
            start_time = time.perf_counter()
            saved_text = load_saved_document(saved_record)

            print(
                f"Saved document loading: "
                f"{time.perf_counter() - start_time:.2f} seconds"
            )

            if saved_text and policy_content_is_relevant(
                Path(saved_record["file_path"]).stem,
                saved_text,
                policy_type,
            ):
                print("Using a recently checked saved document.")

                ask_question(
                    question=original_question,
                    document_text=saved_text,
                    source=saved_url,
                )
                return

    print("\nNo suitable fresh saved document. Searching the web...")

    # B. Search for official-domain candidates.
    search_result = search_company_policy(
        company,
        policy_type,
        max_results=10,
    )

    candidates = search_result.get("official_candidates", [])

    if not candidates:
        print(
            "\nNo matching official-domain candidates were found."
        )
        print(
            "This does not prove the company has no policy. "
            "A suitable public source could not be verified."
        )
        return

    # C. Extract, validate and save a suitable document.
    for candidate in candidates:
        url = candidate.get("url", "")

        if not url or not is_official_domain(url, allowed_domains):
            continue

        try:
            start_time = time.perf_counter()
            document = load_document(url)

            print(
                f"Document extraction: "
                f"{time.perf_counter() - start_time:.2f} seconds"
            )

            if not policy_content_is_relevant(
                document["title"],
                document["text"],
                policy_type,
            ):
                print(f"Skipping unrelated page: {document['title']}")
                continue

            original_bytes, content_type = download_original(
                url,
                allowed_domains,
            )

            filename = get_filename(
                document["title"],
                content_type,
                url,
            )

            save_original_document(
                company=company,
                policy_type=policy_type,
                source_url=url,
                content=original_bytes,
                filename=filename,
                last_checked=datetime.now(timezone.utc).isoformat(),
            )

            print(f"\nDocument title: {document['title']}")
            print(f"Source: {url}")
            print("Basic policy relevance check passed.")
            print("Original document saved.")

            # D. Generate an answer using the original question and text.
            ask_question(
                question=original_question,
                document_text=document["text"],
                source=url,
            )
            return

        except (
            requests.RequestException,
            ValueError,
            OSError,
        ) as exc:
            print(f"Could not use candidate {url}: {exc}")

        except Exception as exc:
            print(f"Unexpected error for {url}: {exc}")

    print(
        "\nNo accessible candidate passed the basic relevance check."
    )
    print(
        "Try rephrasing the question or verify a suitable official "
        "policy source manually."
    )


# --------------------------------------------------
# 8. Interactive natural-language interface
# --------------------------------------------------

if __name__ == "__main__":

    print("Agentic AI Company Policy Assistant — Groq")
    print("Ask a question in your own words.")
    print("Type 'exit' to stop.\n")

    while True:
        user_prompt = input("Your question: ").strip()

        if user_prompt.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break

        if not user_prompt:
            print("Please enter a question.")
            continue

        try:
            details = understand_user_query(user_prompt)

            run_agent(
                company=details["company"],
                policy_type=details["policy_type"],
                original_question=user_prompt,
            )

        except ValueError as exc:
            print(f"\nCould not process question: {exc}")

        except Exception as exc:
            print(f"\nRequest failed: {type(exc).__name__}: {exc}")
