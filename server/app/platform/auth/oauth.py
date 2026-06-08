"""Authlib OAuth client for Google, configured via OIDC discovery.

Discovery URL lets Authlib fetch Google's authorization,
token, and userinfo endpoints automatically.
"""

from __future__ import annotations

from functools import lru_cache

from authlib.integrations.starlette_client import OAuth

from app.platform.config import get_settings

GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

@lru_cache
def get_oauth() -> OAuth:
    settings = get_settings()
    oauth = OAuth()
    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        server_metadata_url=GOOGLE_DISCOVERY_URL,
        client_kwargs={"scope": "openid email profile"},
    )
    return oauth
