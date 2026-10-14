"""Best-effort reading of a link's title and description.

Used when capturing a Link item: we fetch the page, pull the <title> and an
og:description / meta description, and fill in fields the user left empty.
If the destination is slow, blocks, or refuses the request, we quietly give up
and keep hiding behind the URL — the capture still succeeds either way.
"""

import html.parser
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

MAX_BYTES = 262144          # 256 KB of head matter is plenty for a title
TIMEOUT = 6.0               # seconds; don't make saves wait forever
TITLE_CHARS = 200
DESCRIPTION_CHARS = 300

USER_AGENT = "Mozilla/5.0 (compatible; attic/1.0; personal knowledge base)"


def _ip_blocked(ip_text: str) -> bool:
    """True for loopback, private, link-local, reserved and multicast ranges."""
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return True
    checks = ("is_loopback", "is_private", "is_link_local", "is_reserved",
              "is_multicast", "is_unspecified")
    return any(getattr(ip, name, False) for name in checks)


def _resolve_ips(hostname: str) -> list:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, socket.timeout, OSError):
        return []
    return [info[4][0] for info in infos]


def _host_blocked(hostname: str) -> bool:
    """Reject private/internal hosts so a link can't target the network itself."""
    if not hostname:
        return True
    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        pass  # hostname, resolve it below
    else:
        return _ip_blocked(ip.exploded)
    for ip in _resolve_ips(hostname):
        if _ip_blocked(ip):
            return True
    return False


def _safe_url(url: str) -> Optional[urllib.parse.ParseResult]:
    try:
        parsed = urllib.parse.urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    if _host_blocked(parsed.hostname):
        return None
    return parsed


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Refuse redirects that would leave public hosts for internal ones."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = _safe_url(newurl)
        if parsed is None:
            return None  # stop the redirect chain
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_SafeRedirectHandler())


def _charset_of(content_type: str) -> str:
    match = re.search(r"charset=([\w.-]+)", content_type or "", re.IGNORECASE)
    return match.group(1) if match else "utf-8"


class _MetaParser(html.parser.HTMLParser):
    """Pulls <title> and the earliest description meta tag without buffering."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title: Optional[str] = None
        self.description: Optional[str] = None
        self._capturing = False
        self._parts: list[str] = []
        self._seen = 0
        self._cap = 120_000

    def handle_starttag(self, tag, attrs):
        if tag == "title" and self.title is None:
            self._capturing = True
            self._parts = []
        elif tag == "meta":
            data = dict(attrs)
            key = (data.get("name") or data.get("property") or "").strip().lower()
            content = (data.get("content") or "").strip()
            if key in ("description", "og:description") and content and self.description is None:
                self.description = content[:DESCRIPTION_CHARS]
            elif tag == "meta" and data.get("charset") and self.description is None:
                pass  # charset handled separately; keep parser simple

    def handle_data(self, data):
        if self._capturing:
            self._seen += len(data)
            if self._seen > self._cap:
                self._capturing = False
                return
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag == "title" and self._capturing:
            self._capturing = False
            text = " ".join("".join(self._parts).split())
            if text:
                self.title = text[:TITLE_CHARS]


def fetch_link_metadata(url: str) -> Optional[dict]:
    """Return {"title", "description"} or None if the page can't be read."""
    parsed = _safe_url(url)
    if parsed is None:
        return None

    request = urllib.request.Request(
        url.strip(),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Charset": "utf-8",
        },
    )
    try:
        with _opener.open(request, timeout=TIMEOUT) as resp:
            ctype = resp.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if ctype not in ("text/html", "application/xhtml+xml", ""):
                return None  # PDF, image, blob, etc. — nothing useful for a title
            raw = resp.read(MAX_BYTES)
            charset = _charset_of(resp.headers.get("Content-Type", ""))
    except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout, TimeoutError, OSError, ValueError):
        return None

    parser = _MetaParser()
    parser.feed(raw.decode(charset, errors="replace"))

    if not (parser.title or parser.description):
        return None
    return {"title": parser.title or "", "description": parser.description or ""}