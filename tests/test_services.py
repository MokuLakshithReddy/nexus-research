from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services import ArticleTextParser, simple_summary, validate_public_url


def test_article_parser_skips_script_and_collects_text():
    parser = ArticleTextParser()
    parser.feed("<html><title>Research Title</title><script>ignore this</script><main><h1>Evidence</h1><p>Useful research text.</p></main></html>")
    assert "Research Title" in " ".join(parser.title_parts)
    extracted = " ".join(parser.parts)
    assert "Useful research text." in extracted
    assert "ignore this" not in extracted


def test_simple_summary_keeps_source_markers():
    sources = [{"id": 9, "title": "Study", "content": "A detailed finding about the research topic that contains enough words to be useful. Another detailed finding explains a separate issue with adequate context.", "relevance": .7}]
    summary = simple_summary(sources)
    assert "[Source 9]" in summary


def test_validate_public_url_rejects_local_hosts():
    try:
        validate_public_url("http://localhost:8000/admin")
    except ValueError as exc:
        assert "Local" in str(exc)
    else:
        raise AssertionError("localhost must be rejected")


def test_validate_public_url_rejects_non_http_schemes():
    try:
        validate_public_url("file:///etc/passwd")
    except ValueError as exc:
        assert "HTTP" in str(exc)
    else:
        raise AssertionError("file: URLs must be rejected")
