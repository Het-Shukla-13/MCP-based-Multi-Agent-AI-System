"""
Web MCP server: free web search (ddgs metasearch, no API key) and page reading.

SSRF protection: fetch_page refuses URLs that resolve to private, loopback,
link-local or reserved addresses (e.g. http://localhost:8010 = our own API,
or cloud metadata at 169.254.169.254). Redirects are re-checked on every hop.
"""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS
from loguru import logger
from mcp.server.fastmcp import FastMCP

from app.mcp_servers.common import configure_server_logging, truncate

configure_server_logging("web")
mcp = FastMCP("web")

USER_AGENT = "Mozilla/5.0 (compatible; MultiAgentAssistant/1.0)"
MAX_REDIRECTS = 4
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024


def is_public_url(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False, "Only http(s) URLs with a host are allowed."
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror:
        return False, f"Cannot resolve host '{parsed.hostname}'."
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:  # covers private, loopback, link-local, reserved, multicast
            return False, f"Refusing to fetch non-public address {ip} (SSRF protection)."
    return True, ""


SEARCH_BACKENDS = ("auto", "bing", "google", "brave", "yahoo", "duckduckgo")
WIKIPEDIA_SEARCH = "https://en.wikipedia.org/w/rest.php/v1/search/page"


def _ddgs_search(query: str, max_results: int, news: bool) -> tuple[list[dict], str]:
    """Free metasearch scrapes public engines, which rate-limit intermittently,
    so try several engines one by one before giving up."""
    errors = []
    with DDGS(timeout=10) as ddgs:
        if news:
            try:
                return list(ddgs.news(query, max_results=max_results)), "ddgs-news"
            except Exception as exc:
                errors.append(f"news: {exc}")
        for backend in SEARCH_BACKENDS:
            try:
                results = list(ddgs.text(query, max_results=max_results, backend=backend))
                if results:
                    return results, f"ddgs-{backend}"
            except Exception as exc:
                errors.append(f"{backend}: {exc}")
    return [], "; ".join(errors)[:300]


async def _wikipedia_search(query: str, max_results: int) -> list[dict]:
    """Official, free, keyless API: the dependable fallback when engines block us."""
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
        response = await client.get(WIKIPEDIA_SEARCH, params={"q": query, "limit": max_results})
        response.raise_for_status()
    results = []
    for page in response.json().get("pages", []):
        excerpt = BeautifulSoup(page.get("excerpt") or "", "html.parser").get_text()
        results.append({
            "title": page.get("title", ""),
            "href": f"https://en.wikipedia.org/wiki/{page.get('key', '')}",
            "body": (page.get("description") or "") + " - " + excerpt,
        })
    return results


@mcp.tool()
async def web_search(query: str, max_results: int = 5, news: bool = False) -> str:
    """Search the web (free). Returns title, URL and snippet for each result.
    Set news=true for recent news. Use fetch_page to read a result in full."""
    max_results = max(1, min(max_results, 10))
    results, source = await asyncio.to_thread(_ddgs_search, query, max_results, news)
    if not results:
        logger.warning("Web search engines unavailable ({}); falling back to Wikipedia", source)
        try:
            results, source = await _wikipedia_search(query, max_results), "wikipedia"
        except Exception as exc:
            logger.warning("Wikipedia search failed: {}", exc)
    if not results:
        return "Web search is unavailable right now. Answer from your own knowledge and say so."
    lines = [
        f"{i}. {r.get('title', '')}\n   URL: {r.get('href') or r.get('url', '')}\n"
        f"   {(r.get('date', '') + ' ') if news else ''}{r.get('body', '')}"
        for i, r in enumerate(results, 1)
    ]
    note = " (general web engines were unavailable; results are from Wikipedia)" if source == "wikipedia" else ""
    return truncate(f"Search results for: {query}{note}\n\n" + "\n".join(lines))


@mcp.tool()
async def fetch_page(url: str, max_chars: int = 8000) -> str:
    """Download a public web page and return its readable text (scripts/navigation removed)."""
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, headers={"User-Agent": USER_AGENT}) as client:
        for _ in range(MAX_REDIRECTS + 1):
            ok, reason = await asyncio.to_thread(is_public_url, url)
            if not ok:
                return reason
            response = await client.get(url)
            if response.is_redirect:
                url = urljoin(url, response.headers.get("location", ""))
                continue
            break
        else:
            return "Too many redirects."

    if response.status_code >= 400:
        return f"Could not fetch page: HTTP {response.status_code}"
    if "html" not in response.headers.get("content-type", "") and "text" not in response.headers.get("content-type", ""):
        return f"Unsupported content type: {response.headers.get('content-type')}"
    html = response.content[:MAX_DOWNLOAD_BYTES].decode(response.encoding or "utf-8", "replace")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else url
    text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    return f"# {title}\nSource: {url}\n\n" + truncate(text, max(500, min(max_chars, 20_000)))


if __name__ == "__main__":
    mcp.run()
