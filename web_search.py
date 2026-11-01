
from ddgs import DDGS
from urllib.parse import urlparse, urlunparse
from typing import Any
import time


# --------------------------------------------------
# 1. Verified company domain allowlist
# --------------------------------------------------

KNOWN_COMPANY_DOMAINS = {
    "amazon": [
        "amazon.com",
        "aboutamazon.com",
        "amazon.jobs",
    ],
    "google": [
        "google.com",
        "about.google",
        "careers.google.com",
    ],
    "microsoft": [
        "microsoft.com",
        "careers.microsoft.com",
    ],
    "apple": [
        "apple.com",
        "jobs.apple.com",
    ],
    "meta": [
        "meta.com",
        "metacareers.com",
    ],
}


# --------------------------------------------------
# 2. Company/domain helpers
# --------------------------------------------------

def normalize_company_name(company: str) -> str:
    return " ".join(company.strip().lower().split())


def get_known_domains(company: str) -> list[str]:
    return KNOWN_COMPANY_DOMAINS.get(
        normalize_company_name(company),
        [],
    )


def is_official_domain(url: str, domains: list[str]) -> bool:
    """Check whether the HTTPS URL belongs to an allowlisted domain."""

    try:
        parsed = urlparse(url)

        if parsed.scheme.lower() != "https" or not parsed.hostname:
            return False

        host = parsed.hostname.lower().rstrip(".")

        return any(
            host == domain.lower()
            or host.endswith("." + domain.lower())
            for domain in domains
        )

    except (ValueError, TypeError, AttributeError):
        return False


def normalize_url(url: str) -> str:
    """Remove query strings and fragments for duplicate detection."""

    try:
        parsed = urlparse(url.strip())

        return urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            "",
            "",
        ))

    except (ValueError, AttributeError):
        return url.strip()


# --------------------------------------------------
# 3. Search DuckDuckGo
# --------------------------------------------------

def search_web(
    query: str,
    max_results: int = 8,
) -> list[dict[str, str]]:
    """Return normalized search results; failures return an empty list."""

    try:
        with DDGS(timeout=15) as ddgs:
            results = ddgs.text(
                query,
                max_results=max_results,
                region="us-en",
                safesearch="off",
            )

            normalized_results = []

            for result in results or []:
                url = result.get("href") or result.get("url") or ""

                if not url:
                    continue

                normalized_results.append({
                    "title": result.get("title", ""),
                    "url": url,
                    "snippet": result.get("body", ""),
                })

            return normalized_results

    except Exception as exc:
        print(f"Search failed for query '{query}': {exc}")
        return []


# --------------------------------------------------
# 4. Build multiple search queries
# --------------------------------------------------

def build_policy_queries(
    company: str,
    policy_type: str,
    domains: list[str],
) -> list[str]:
    """Build varied searches instead of combining every domain in one query."""

    queries = [
        f'"{company}" "{policy_type}" employee policy',
        f'"{company}" employee benefits {policy_type}',
        f'{company} official employee {policy_type} information',
        f'{company} careers benefits {policy_type}',
    ]

    # Search each approved domain independently.
    for domain in domains:
        queries.append(
            f'site:{domain} "{policy_type}" employee'
        )
        queries.append(
            f'site:{domain} "{policy_type}" benefits'
        )

    # Preserve order while removing duplicate queries.
    return list(dict.fromkeys(queries))


# --------------------------------------------------
# 5. Search for company policies
# --------------------------------------------------

def search_company_policy(
    company: str,
    policy_type: str,
    max_results: int = 8,
) -> dict[str, Any]:

    company = company.strip()
    policy_type = policy_type.strip()

    if not company or not policy_type:
        return {
            "status": "invalid_input",
            "message": "Enter a company and policy topic.",
            "official_candidates": [],
            "other_results": [],
        }

    domains = get_known_domains(company)

    if not domains:
        return {
            "status": "unknown_company_domain",
            "message": (
                f"No approved domain is configured for {company}. "
                "Verify the company's official website and add its "
                "domain to KNOWN_COMPANY_DOMAINS."
            ),
            "official_candidates": [],
            "other_results": [],
        }

    queries = build_policy_queries(
        company,
        policy_type,
        domains,
    )

    all_results = []
    seen_urls = set()

    print(f"\nSearching for {company}: {policy_type}")
    print(f"Search queries prepared: {len(queries)}")

    for index, query in enumerate(queries, start=1):
        print(f"\nSearch {index}/{len(queries)}: {query}")

        results = search_web(
            query=query,
            max_results=max_results,
        )

        # Retry once if the first attempt returns no results.
        if not results:
            time.sleep(1)
            results = search_web(
                query=query,
                max_results=max_results,
            )

        if not results:
            print("No results from this query; trying the next one.")
            continue

        for result in results:
            url = result["url"]

            if not url.startswith("https://"):
                continue

            normalized = normalize_url(url)

            if normalized in seen_urls:
                continue

            seen_urls.add(normalized)
            all_results.append(result)

        # Stop early once enough results have been collected.
        if len(all_results) >= max_results * 3:
            break

        # Small pause to reduce rapid repeated requests.
        time.sleep(0.3)

    official_candidates = []
    other_results = []

    for result in all_results:
        if is_official_domain(result["url"], domains):
            official_candidates.append(result)
        else:
            other_results.append(result)

    if official_candidates:
        return {
            "status": "official_candidates_found",
            "message": (
                "Potential official-domain pages were found. "
                "The agent must still check whether the page contains "
                "relevant policy information."
            ),
            "official_candidates": official_candidates,
            "other_results": other_results,
        }

    return {
        "status": "no_official_candidates_found",
        "message": (
            f"No suitable pages were found on the approved domains "
            f"for {company}'s {policy_type} topic. This does not mean "
            "the company has no such policy. Check the search "
            "connection or verify another official domain."
        ),
        "official_candidates": [],
        "other_results": other_results,
    }


# --------------------------------------------------
# 6. Display search results
# --------------------------------------------------

def display_results(result: dict[str, Any]) -> None:
    print("\nStatus:", result["status"])
    print(result["message"])

    for heading, key in [
        ("Potential official sources", "official_candidates"),
        ("Other search results", "other_results"),
    ]:
        print(f"\n--- {heading} ---")

        items = result.get(key, [])

        if not items:
            print("No results.")
            continue

        for index, item in enumerate(items, start=1):
            print(f"\n{index}. {item['title']}")
            print("URL:", item["url"])
            print("Snippet:", item["snippet"])


# --------------------------------------------------
# 7. Standalone search test
# --------------------------------------------------

if __name__ == "__main__":
    print("Company Policy Web Search")

    company = input("Company name: ").strip()
    policy_type = input("Policy topic: ").strip()

    result = search_company_policy(
        company=company,
        policy_type=policy_type,
        max_results=5,
    )

    display_results(result)
