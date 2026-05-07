from unittest.mock import patch, MagicMock

from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_edge import KnowledgeEdge
from app.services.knowledge_engine.concept_linker import VALID_RELATION_TYPES
from app.services.knowledge_engine.context_query import _extract_keywords
from app.config import get_settings


def test_knowledge_document_model():
    assert hasattr(KnowledgeDocument, "__tablename__")
    assert KnowledgeDocument.__tablename__ == "knowledge_documents"

    expected_columns = [
        "id", "title", "file_name", "file_path", "file_format",
        "file_size_bytes", "content_hash", "category", "tags",
        "authors", "language", "page_count", "section_count",
        "parse_status", "parse_errors", "wiki_status",
        "knowledge_extracted", "source_type", "source_url",
        "related_paper_id", "is_active", "created_at", "updated_at",
    ]
    mapper = KnowledgeDocument.__table__
    existing = {c.name for c in mapper.columns}
    for col in expected_columns:
        assert col in existing, f"Missing column: {col}"


def test_knowledge_edge_model():
    assert hasattr(KnowledgeEdge, "__tablename__")
    assert KnowledgeEdge.__tablename__ == "knowledge_edges"

    expected_columns = [
        "id", "source_concept", "target_concept", "relation_type",
        "strength", "evidence", "source_document_id",
        "is_verified", "created_at",
    ]
    mapper = KnowledgeEdge.__table__
    existing = {c.name for c in mapper.columns}
    for col in expected_columns:
        assert col in existing, f"Missing column: {col}"


def test_knowledge_edge_relation_types():
    assert len(VALID_RELATION_TYPES) == 6
    expected = {"depends_on", "extends", "contradicts", "analogous", "part_of", "evolves_from"}
    assert set(VALID_RELATION_TYPES) == expected
    for rt in VALID_RELATION_TYPES:
        assert isinstance(rt, str)
        assert len(rt) > 0


def test_context_query_basic():
    keywords = _extract_keywords("什么是机器学习算法")
    assert len(keywords) > 0
    assert any("机器" in kw or "算法" in kw for kw in keywords)

    keywords_empty = _extract_keywords("")
    assert keywords_empty == []

    keywords_en = _extract_keywords("deep learning neural network")
    assert any(kw in keywords_en for kw in ["deep", "learning", "neural", "network"])


def test_knowledge_engine_singleton():
    from app.services.knowledge_engine import knowledge_engine, KnowledgeEngine
    assert knowledge_engine is not None
    assert isinstance(knowledge_engine, KnowledgeEngine)
    assert hasattr(knowledge_engine, "extract")
    assert hasattr(knowledge_engine, "query_for_context")
    assert hasattr(knowledge_engine, "get_graph_data")
    assert hasattr(knowledge_engine, "get_stats")
    assert hasattr(knowledge_engine, "ingest_from_conversation")


def test_config_settings():
    settings = get_settings()
    assert hasattr(settings, "knowledge_base_path")
    assert hasattr(settings, "knowledge_max_context_chars")
    assert hasattr(settings, "knowledge_enhanced_context_chars")
    assert hasattr(settings, "knowledge_extraction_max_tokens")
    assert hasattr(settings, "knowledge_graph_max_depth")
    assert hasattr(settings, "knowledge_auto_extract")
    assert hasattr(settings, "knowledge_dedup_enabled")
    assert isinstance(settings.knowledge_max_context_chars, int)
    assert isinstance(settings.knowledge_enhanced_context_chars, int)
    assert isinstance(settings.knowledge_auto_extract, bool)
    assert isinstance(settings.knowledge_dedup_enabled, bool)
