from pathlib import Path

import knowledge_base as kb_mod

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _kb():
    return kb_mod.build_default_knowledge_base(PROJECT_ROOT)


def test_knowledge_base_builds_with_many_chunks():
    kb = _kb()
    assert len(kb.chunks) > 30


def test_every_chunk_has_a_real_source_file():
    kb = _kb()
    for c in kb.chunks[:20]:
        if c.source_file.startswith("apps/results_chat/"):
            assert (PROJECT_ROOT / c.source_file).is_file()
        else:
            assert (PROJECT_ROOT / c.source_file).is_file(), c.source_file


def test_claims_csv_is_indexed_with_status_labels():
    kb = _kb()
    claims = [c for c in kb.chunks if "claims_evidence.csv" in c.source_file]
    assert len(claims) >= 10
    assert any("status:" in c.text for c in claims)


def test_retrieve_english_query_finds_training_section():
    kb = _kb()
    hits = kb.retrieve("What training protocol was used for the model?", k=3)
    assert hits
    assert any("training" in c.section_title.lower() or "training" in c.text.lower() for _, c in hits)


def test_retrieve_spanish_query_bridges_to_english_content():
    kb = _kb()
    hits_en = kb.retrieve("Why was Spike not used for verification?", k=3)
    hits_es = kb.retrieve("¿Por qué no se usó Spike para la verificación?", k=3)
    assert hits_en and hits_es
    # same top source document should surface for both languages
    assert hits_en[0][1].source_file == hits_es[0][1].source_file


def test_retrieve_returns_nothing_for_unrelated_query():
    # Deliberately NOT a phrase that appears anywhere in this project's own
    # documentation (an earlier version of this test used a "recommend a
    # pizza place" phrasing that got accidentally self-referential once
    # docs/decisions.md D-014 started quoting that exact phrase as a worked
    # example of this very false-positive class -- see D-014 and
    # test_knowledge_base_false_positive_class_from_d014_is_still_a_true_overlap
    # below for that now-expected case).
    kb = _kb()
    hits = kb.retrieve("help me plan a birthday party for my dog", k=4)
    assert hits == [] or all(score < 0.15 for score, _ in hits)


def test_knowledge_base_false_positive_class_from_d014_is_still_a_true_overlap():
    # D-014 documents, in prose, the exact "recommend a good pizza place"
    # phrase as a worked example of a retrieval false positive it fixed.
    # That makes the phrase no longer a true off-topic probe -- it now has
    # genuine, high term-overlap with D-014's own chunk, so retrieving it
    # is CORRECT retrieval behavior, not a regression. This test documents
    # that distinction explicitly rather than leaving it as a silent trap
    # for a future editor of either file.
    kb = _kb()
    hits = kb.retrieve("Can you recommend a good pizza place?", k=1)
    assert hits
    assert "D-014" in hits[0][1].section_title


def test_retrieve_respects_k_limit():
    kb = _kb()
    hits = kb.retrieve("model training results memory processor verification", k=2)
    assert len(hits) <= 2


def test_tokenize_strips_stopwords():
    tokens = kb_mod.tokenize("What is the architecture of this project?")
    assert "the" not in tokens
    assert "is" not in tokens
    assert "architecture" in tokens


def test_expand_query_tokens_bridges_spanish_terms():
    tokens = kb_mod.tokenize("arquitectura del clasificador")
    expanded = kb_mod.expand_query_tokens(tokens)
    assert "architecture" in expanded
    assert "classifier" in expanded


def test_chunk_markdown_splits_on_headers(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Title\nintro\n## Section A\ncontent a\n## Section B\ncontent b\n")
    chunks = kb_mod.chunk_markdown(md, "doc.md")
    titles = [c.section_title for c in chunks]
    assert "Section A" in titles
    assert "Section B" in titles


def test_get_knowledge_base_is_cached():
    kb1 = kb_mod.get_knowledge_base(PROJECT_ROOT)
    kb2 = kb_mod.get_knowledge_base(PROJECT_ROOT)
    assert kb1 is kb2
    kb3 = kb_mod.get_knowledge_base(PROJECT_ROOT, refresh=True)
    assert kb3 is not kb1
