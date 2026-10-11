"""The fetch guard: only public http(s) addresses, on the first request and on every
redirect hop. No network: addresses are IP literals, and redirects use a mock transport.
"""

import sys

import httpx
import pytest

import app.tools.fetch_url  # noqa: F401  (registers the module; `app.tools.fetch_url` is the tool)

fetch_mod = sys.modules["app.tools.fetch_url"]

PUBLIC = "http://93.184.216.34"


class TestRequirePublic:
    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data",  # cloud metadata
            "http://127.0.0.1:8000/",
            "http://10.0.0.1/x",
            "http://192.168.1.1/",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",  # IPv4-mapped loopback
            "http://localhost/",
            "file:///etc/passwd",
            "ftp://93.184.216.34/",
            "http:///nohost",
        ],
    )
    async def test_non_public_or_non_http_is_blocked(self, url):
        with pytest.raises(fetch_mod.BlockedURL):
            await fetch_mod._require_public(url)

    async def test_public_ip_literal_is_allowed(self):
        await fetch_mod._require_public(f"{PUBLIC}/page")


def mock_client(monkeypatch, handler) -> list[str]:
    seen: list[str] = []
    real = httpx.AsyncClient

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return handler(request)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(wrapped), **kw)
    )
    return seen


class TestRedirects:
    async def test_redirect_to_an_internal_address_is_not_followed(self, monkeypatch):
        seen = mock_client(
            monkeypatch,
            lambda r: httpx.Response(302, headers={"location": "http://169.254.169.254/latest"}),
        )

        with pytest.raises(fetch_mod.BlockedURL):
            await fetch_mod._fetch_html(f"{PUBLIC}/start")

        assert seen == [f"{PUBLIC}/start"]  # the internal hop was never requested

    async def test_public_redirects_are_followed(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/start":
                return httpx.Response(301, headers={"location": "/final"})  # relative
            return httpx.Response(200, text="<p>done</p>")

        seen = mock_client(monkeypatch, handler)

        assert await fetch_mod._fetch_html(f"{PUBLIC}/start") == "<p>done</p>"
        assert seen == [f"{PUBLIC}/start", f"{PUBLIC}/final"]

    async def test_redirect_loop_is_cut_off(self, monkeypatch):
        mock_client(monkeypatch, lambda r: httpx.Response(302, headers={"location": "/again"}))

        with pytest.raises(fetch_mod.BlockedURL, match="Too many redirects"):
            await fetch_mod._fetch_html(f"{PUBLIC}/start")

    async def test_error_status_still_raises(self, monkeypatch):
        mock_client(monkeypatch, lambda r: httpx.Response(404))

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_mod._fetch_html.__wrapped__(f"{PUBLIC}/missing")  # skip tenacity backoff


class TestRetry:
    async def test_a_4xx_is_not_retried(self, monkeypatch):
        seen = mock_client(monkeypatch, lambda r: httpx.Response(403))

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_mod._fetch_html(f"{PUBLIC}/paywall")  # through tenacity

        assert len(seen) == 1

    async def test_a_5xx_is_retried(self, monkeypatch):
        seen = mock_client(monkeypatch, lambda r: httpx.Response(503))

        async def no_sleep(_: float) -> None:
            pass

        monkeypatch.setattr(fetch_mod._fetch_html.retry, "sleep", no_sleep)  # type: ignore[attr-defined]

        with pytest.raises(httpx.HTTPStatusError):
            await fetch_mod._fetch_html(f"{PUBLIC}/flaky")

        assert len(seen) == 3

    def test_only_network_errors_and_5xx_are_transient(self):
        from app.tools.sources import is_transient

        def status(code: int) -> httpx.HTTPStatusError:
            request = httpx.Request("GET", "https://x.test")
            return httpx.HTTPStatusError(
                "", request=request, response=httpx.Response(code, request=request)
            )

        assert is_transient(httpx.ConnectTimeout("t"))
        assert is_transient(httpx.ConnectError("c"))
        assert is_transient(status(503))
        assert not any(is_transient(status(c)) for c in (403, 404, 429))
        assert not is_transient(ValueError("blocked"))
