"""Web tools: fetch a URL, search the web, and make raw HTTP requests.

Uses the standard library only (``urllib``) so there's no extra dependency.
Web search scrapes DuckDuckGo's HTML endpoint (no API key); it's best-effort and
degrades gracefully if the page format changes.
"""
from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import Tool, truncate
from .registry import register_tool

# A browser-like UA; some endpoints (e.g. DuckDuckGo) reject non-browser agents.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def _http_get(url: str, timeout: int = 20) -> tuple[int, str]:
    request = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        charset = response.headers.get_content_charset() or "utf-8"
        return response.status, response.read().decode(charset, "replace")


def _http_post_form(url: str, fields: dict[str, str], timeout: int = 20) -> tuple[int, str]:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=_HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        charset = response.headers.get_content_charset() or "utf-8"
        return response.status, response.read().decode(charset, "replace")


def _html_to_text(markup: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", markup)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _ddg_unwrap(href: str) -> str:
    match = re.search(r"uddg=([^&]+)", href)
    if match:
        return urllib.parse.unquote(match.group(1))
    if href.startswith("//"):
        return "https:" + href
    return href


def _parse_ddg_results(markup: str, limit: int) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    for match in re.finditer(
        r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', markup, re.S
    ):
        title = _html_to_text(match.group(2))
        url = _ddg_unwrap(match.group(1))
        if title and url:
            results.append((title, url))
        if len(results) >= limit:
            break
    return results


@register_tool
class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch a web page and return its readable text content."
    parameters = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "The URL to fetch."}},
        "required": ["url"],
    }

    def run(self, url: str, **_: Any) -> str:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            status, body = _http_get(url)
        except Exception as exc:  # noqa: BLE001 — report network errors to the model
            return f"Error fetching {url}: {exc}"
        return f"[HTTP {status}] {url}\n\n{truncate(_html_to_text(body))}"


@register_tool
class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web (via DuckDuckGo) and return the top result titles and URLs."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "max_results": {
                "type": "integer",
                "description": "Number of results to return (default 5).",
            },
        },
        "required": ["query"],
    }

    def run(self, query: str, max_results: int = 5, **_: Any) -> str:
        # DuckDuckGo's HTML endpoint requires a POST form and a browser UA.
        try:
            _, body = _http_post_form("https://html.duckduckgo.com/html/", {"q": query})
        except Exception as exc:  # noqa: BLE001
            return f"Error searching: {exc}"
        results = _parse_ddg_results(body, max(1, max_results))
        if not results:
            return "No results found (or the search page format changed)."
        return "\n".join(f"{i}. {title}\n   {link}" for i, (title, link) in enumerate(results, 1))


@register_tool
class HttpRequestTool(Tool):
    name = "http_request"
    description = (
        "Make an HTTP request to an API and return the status and response body. "
        "Supports GET/POST/PUT/PATCH/DELETE with optional headers and body."
    )
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "method": {"type": "string", "description": "HTTP method (default GET)."},
            "headers": {"type": "object", "description": "Optional request headers."},
            "body": {
                "type": "string",
                "description": "Optional request body (raw string or JSON text).",
            },
        },
        "required": ["url"],
    }

    def run(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | None = None,
        **_: Any,
    ) -> str:
        data = body.encode("utf-8") if isinstance(body, str) else None
        request = urllib.request.Request(
            url, data=data, method=method.upper(), headers={**_HEADERS, **(headers or {})}
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                charset = response.headers.get_content_charset() or "utf-8"
                text = response.read().decode(charset, "replace")
                return f"[HTTP {response.status}]\n{truncate(text)}"
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            return f"[HTTP {exc.code}] {exc.reason}\n{truncate(detail)}"
        except Exception as exc:  # noqa: BLE001
            return f"Error: {exc}"
