"""Markdown to safe HTML.

We render Markdown with the free "markdown" library, then run the result
through "bleach" to strip anything dangerous. Stored HTML is never trusted:
everything goes through here before it reaches the browser, so a note
containing a <script> tag cannot execute.
"""

import re
from typing import Optional

import bleach
import markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name, guess_lexer

# Tags a note is allowed to produce. Anything else is stripped (the text is
# kept, the tag is removed).
ALLOWED_TAGS = [
    "p", "br", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "em", "b", "i", "u", "s", "del", "ins", "mark",
    "blockquote", "pre", "code",
    "ul", "ol", "li",
    "a", "img",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "span", "sup", "sub", "dl", "dt", "dd",
]

ALLOWED_ATTRS = {
    "a": ["href", "title", "rel"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "span": ["class", "style"],
    "th": ["align", "colspan", "rowspan"],
    "td": ["align", "colspan", "rowspan"],
    "ol": ["start"],
    "li": ["class"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

# Inline styles (instead of CSS classes) keep highlighting self-contained and
# theme-agnostic; Pygments colors the text, our CSS keeps the code background.
_EXTENSIONS = ["fenced_code", "codehilite", "tables", "sane_lists"]
_EXTENSION_CONFIGS = {
    "codehilite": {
        "noclasses": True,
        "guess_lang": False,
        "css_class": "highlight",
    },
}

_SNIPPET_FORMATTER = HtmlFormatter(nowrap=True, noclasses=True)

# Kept to a friendly charset so user text can't leak HTML into markup.
_LANGUAGE_RE = re.compile(r"[^a-zA-Z0-9+#_-]+")

# Add rel="noopener noreferrer" to any link that lacks it.
_LINK_RE = re.compile(r"<a (?![^>]*\brel=)", re.IGNORECASE)


def render_markdown(text: str) -> str:
    """Return sanitized HTML for the given Markdown text."""
    text = text or ""
    html = markdown.markdown(
        text,
        extensions=_EXTENSIONS,
        extension_configs=_EXTENSION_CONFIGS,
    )
    cleaned = bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )
    return _LINK_RE.sub('<a rel="noopener noreferrer" ', cleaned)


def render_snippet(code: str, language: Optional[str]) -> str:
    """Return a Pygments-highlighted, self-contained <pre> for snippet items."""
    code = code or ""
    if not code.strip():
        return '<div class="snippet-block"><pre class="snippet-code"><code></code></pre></div>'
    lang = (language or "").strip().lower()
    try:
        lexer = get_lexer_by_name(lang) if lang else guess_lexer(code)
    except Exception:
        lexer = TextLexer()
    body = highlight(code, lexer, _SNIPPET_FORMATTER)
    safe_lang = _LANGUAGE_RE.sub("", lang)[:30]
    label = f'<span class="snippet-lang">{safe_lang}</span>' if safe_lang else ""
    return (
        '<div class="snippet-block">' + label +
        '<pre class="snippet-code"><code>' + body + "</code></pre>" +
        "</div>"
    )


def markdown_to_text(text: str) -> str:
    """Plain text version, used for two-line previews in the list."""
    html = markdown.markdown(text or "", extensions=_EXTENSIONS)
    text_only = bleach.clean(html, tags=[], strip=True)
    return " ".join(text_only.split())
