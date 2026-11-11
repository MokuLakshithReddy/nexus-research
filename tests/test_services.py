from __future__ import annotations

from app.services import ArticleTextParser, chunk_text, simple_summary, validate_public_url


def test_article_parser_skips_script_and_collects_text():
    parser = ArticleTextParser()
    parser.feed("<html><title>Research Title</title><script>ignore this</script><main><h1>Evidence</h1><p>Useful research text.</p></main></html>")
    assert "Research Title" in " ".join(parser.title_parts)
    extracted = " ".join(parser.parts)
    assert "Useful research text." in extracted
    assert "ignore this" not in extracted


def test_chunk_text_bounds_chunks_and_overlaps_context():
    text = " ".join(f"Sentence number {index} describes a research finding with enough detail." for index in range(80))
    chunks = chunk_text(text, max_chars=420, overlap=60)
    assert len(chunks) > 3
    assert all(0 < len(chunk) <= 420 for chunk in chunks)
    assert any(chunks[index][-40:] in chunks[index + 1] for index in range(len(chunks) - 1))


def test_simple_summary_preserves_source_citations():
    chunks = [{
        "source_id": 9,
        "content": "A detailed finding about the research topic contains enough words to be useful. Another detailed finding explains a separate issue with adequate context.",
        "score": 0.7,
    }]
    summary = simple_summary(chunks)
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
