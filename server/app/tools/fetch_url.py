"""Fetch a URL and extract clean main text.

Only public http(s) addresses are fetched: the host is resolved and every address must
be globally routable, and redirects are followed by hand so each hop is checked too.
Without that, a search hit that redirects to `http://169.254.169.254/...` (cloud
metadata) or to an internal service would be fetched for us.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura
from langchain_core.tools import tool
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.platform.config import get_settings
from app.tools.sources import FetchedPage, is_transient

DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (compatible; fact-checking-tool/1.0;"),
}
MAX_REDIRECTS = 5


class BlockedURL(ValueError):
    """The URL is not a public http(s) address. Not retried."""


async def _require_public(url: str) -> None:
    """Raise `BlockedURL` unless `url` is http(s) and every address its host resolves to is public.

    ponytail: the check resolves, then httpx resolves again to connect, so a DNS record
    that flips between the two (rebinding) gets through; close it with an egress policy.
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise BlockedURL(f"Only http(s) URLs are fetched: {url}")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(
            parts.hostname, port, type=socket.SOCK_STREAM
        )
    except socket.gaierror as e:
        raise httpx.ConnectError(str(e)) from e
    for *_, sockaddr in infos:
        ip = ipaddress.ip_address(str(sockaddr[0]).split("%")[0])
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if not ip.is_global:
            raise BlockedURL(f"Refusing to fetch a non-public address: {parts.hostname}")


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception(is_transient),  # BlockedURL and 4xx answers are not retried
)
async def _fetch_html(url: str) -> str:
    settings = get_settings()
    async with httpx.AsyncClient(headers=DEFAULT_HEADERS, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await _require_public(url)
            response = await client.get(url, timeout=settings.http_timeout_seconds)
            location = response.headers.get("location")
            if response.is_redirect and location:
                url = urljoin(str(response.url), location)
                continue
            response.raise_for_status()
            return response.text
    raise BlockedURL(f"Too many redirects (more than {MAX_REDIRECTS})")


@tool
async def fetch_url(url: str) -> FetchedPage:
    """Fetch a URL and return its main article text (boilerplate stripped).

    `text` is empty when the page has no extractable article.
    """
    html = await _fetch_html(url)
    extracted = (
        trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_recall=True,
        )
        or ""
    )
    metadata = trafilatura.extract_metadata(html)
    title = (metadata.title if metadata and metadata.title else "") or ""

    return FetchedPage(url=url, title=title, text=extracted)
