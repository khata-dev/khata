"""Markdown rendering helper.

Uses markdown-it-py with a CommonMark baseline plus a few pragmatic extensions:
- tables
- strikethrough
- fenced code
- auto-linking bare URLs

HTML in the source is escaped — we never inline arbitrary HTML into the DOM.
Attribute safety is handled by markdown-it's default sanitiser config.
"""

from __future__ import annotations

from markdown_it import MarkdownIt

_md = (
    MarkdownIt("commonmark", {"html": False, "linkify": True, "breaks": True})
    .enable("strikethrough")
    .enable("table")
)


def render(body_md: str) -> str:
    """Render a markdown string to HTML. Returns empty string for falsy input."""
    if not body_md:
        return ""
    return _md.render(body_md)
