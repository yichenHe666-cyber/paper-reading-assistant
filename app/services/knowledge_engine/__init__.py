import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.session import SessionLocal
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_edge import KnowledgeEdge
from app.services.knowledge_engine.extractor import extract_knowledge
from app.services.knowledge_engine.concept_linker import link_concepts
from app.services.knowledge_engine.graph_builder import KnowledgeGraphBuilder
from app.services.knowledge_engine.wiki_compiler import compile_to_wiki
from app.services.knowledge_engine.context_query import query_for_context as _query_for_context

logger = logging.getLogger(__name__)


class KnowledgeEngine:

    def __init__(self):
        self._graph_builder = KnowledgeGraphBuilder()

    def extract(self, document_id: int) -> dict:
        db = SessionLocal()
        try:
            doc = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.id == document_id,
                KnowledgeDocument.is_active == True,
            ).first()
            if not doc:
                return {"status": "error", "message": f"文档 {document_id} 不存在"}

            from app.services.document_parser.models import ParsedDocument
            parsed_doc = ParsedDocument(
                title=doc.title or "",
                content="",
                sections=[],
                metadata={
                    "file_name": doc.file_name,
                    "file_format": doc.file_format,
                    "category": doc.category,
                    "authors": doc.authors,
                },
            )

            from pathlib import Path
            file_path = Path(doc.file_path)
            if file_path.exists():
                try:
                    parsed_doc.content = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    try:
                        parsed_doc.content = file_path.read_text(encoding="latin-1")
                    except Exception:
                        parsed_doc.content = ""

            settings = get_settings()
            wiki_base = Path(settings.knowledge_base_path)
            existing_wiki_context = ""
            concepts_dir = wiki_base / "wiki" / "concepts"
            if concepts_dir.exists():
                parts = []
                for f in list(concepts_dir.glob("*.md"))[:20]:
                    parts.append(f.read_text(encoding="utf-8")[:300])
                existing_wiki_context = "\n---\n".join(parts)

            memory_context = ""
            try:
                from app.services.memory_engine import memory_engine
                memory_context = memory_engine.recall_for_context(db, call_type="knowledge_extraction", max_chars=1000)
            except Exception:
                pass

            knowledge = extract_knowledge(
                parsed_doc=parsed_doc,
                existing_wiki_context=existing_wiki_context,
                memory_context=memory_context,
            )

            existing_concepts = []
            try:
                rows = db.query(KnowledgeEdge.source_concept).distinct().all()
                existing_concepts = [r[0] for r in rows]
                rows2 = db.query(KnowledgeEdge.target_concept).distinct().all()
                for r in rows2:
                    if r[0] not in existing_concepts:
                        existing_concepts.append(r[0])
            except Exception:
                pass

            new_concept_names = [
                c.get("name", "") for c in knowledge.get("concepts", [])
            ]

            edges = link_concepts(
                new_concepts=knowledge.get("concepts", []),
                existing_concepts=existing_concepts,
            )

            db_edges = self._graph_builder.add_edges(
                edges=edges,
                document_id=document_id,
                db=db,
            )

            wiki_result = compile_to_wiki(
                document=doc,
                knowledge=knowledge,
                edges=edges,
            )

            doc.knowledge_extracted = True
            doc.wiki_status = "compiled"
            doc.updated_at = datetime.now()
            db.commit()

            try:
                from app.services.memory_engine import memory_engine
                for concept in knowledge.get("concepts", []):
                    name = concept.get("name", "")
                    definition = concept.get("definition", "")
                    if name and definition:
                        memory_engine.remember(
                            db,
                            memory_type="connection",
                            title=f"知识概念: {name}",
                            content=definition,
                            tags=["knowledge", "concept", name],
                            source_paper_id=document_id,
                            source_type="knowledge_extraction",
                            confidence=0.8,
                        )
                for chain in knowledge.get("causal_chains", []):
                    cause = chain.get("cause", "")
                    effect = chain.get("effect", "")
                    reasoning = chain.get("reasoning", "")
                    if cause and effect:
                        memory_engine.remember(
                            db,
                            memory_type="direction",
                            title=f"因果链: {cause} → {effect}",
                            content=reasoning or f"{cause} 导致 {effect}",
                            tags=["knowledge", "causal_chain"],
                            source_paper_id=document_id,
                            source_type="knowledge_extraction",
                            confidence=0.7,
                        )
                for method in knowledge.get("methods", []):
                    mname = method.get("name", "")
                    desc = method.get("description", "")
                    if mname and desc:
                        memory_engine.remember(
                            db,
                            memory_type="connection",
                            title=f"方法: {mname}",
                            content=desc,
                            tags=["knowledge", "method"],
                            source_paper_id=document_id,
                            source_type="knowledge_extraction",
                            confidence=0.75,
                        )
            except Exception as e:
                logger.warning(f"知识提取后记忆生成失败: {e}")

            return {
                "status": "ok",
                "document_id": document_id,
                "concepts_count": len(knowledge.get("concepts", [])),
                "methods_count": len(knowledge.get("methods", [])),
                "causal_chains_count": len(knowledge.get("causal_chains", [])),
                "edges_count": len(db_edges),
                "wiki_result": wiki_result,
            }
        except Exception as e:
            db.rollback()
            logger.error(f"知识提取失败 document_id={document_id}: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def query_for_context(self, query: str, enhanced: bool = False) -> str:
        return _query_for_context(query=query, enhanced=enhanced)

    def ingest_from_conversation(self, content: str, source_session_id: int) -> dict:
        db = SessionLocal()
        try:
            from app.services.llm_utils import _call_llm, parse_llm_json_response

            prompt = f"""你是一个知识归档助手。从以下对话内容中提取值得长期保存的知识点。

对话内容：
{content[:3000]}

请以 JSON 返回（只返回 JSON，不要代码块）：
{{
  "concepts": [
    {{"name": "概念名", "name_en": "English name", "definition": "定义", "one_sentence": "一句话理解", "category": "类别", "source_location": "对话"}}
  ],
  "methods": [
    {{"name": "方法名", "description": "描述", "steps": ["步骤1"], "applicable_conditions": "适用条件", "source_location": "对话"}}
  ],
  "practical_points": [
    {{"point": "要点", "value": "价值", "conditions": "条件", "source_location": "对话"}}
  ]
}}

规则：
- 只提取有长期价值的知识点，忽略寒暄和临时信息
- 每个条目必须有 source_location
- 中文输出
"""
            messages = [{"role": "user", "content": prompt}]
            llm_content, usage = _call_llm(messages, max_tokens=3000)
            knowledge = parse_llm_json_response(llm_content, "conversation_ingest")

            existing_concepts = []
            try:
                rows = db.query(KnowledgeEdge.source_concept).distinct().all()
                existing_concepts = [r[0] for r in rows]
            except Exception:
                pass

            edges = link_concepts(
                new_concepts=knowledge.get("concepts", []),
                existing_concepts=existing_concepts,
            )

            db_edges = []
            if edges:
                db_edges = self._graph_builder.add_edges(
                    edges=edges,
                    document_id=None,
                    db=db,
                )

            wiki_base = get_settings().knowledge_base_path
            from pathlib import Path
            from app.services.knowledge_engine.wiki_compiler import _write_file, _slug

            new_pages = 0
            for concept in knowledge.get("concepts", []):
                name = concept.get("name", "")
                if not name:
                    continue
                slug = _slug(name)
                today = datetime.now().strftime("%Y-%m-%d")
                md = f"""---
title: "{name}"
type: concept
category: {concept.get('category', '')}
created: {today}
updated: {today}
tags: [conversation]
sources: ["conversation-{source_session_id}"]
related_concepts: []
---

# {name}

## 定义
{concept.get('definition', '')}

## 一句话理解
> {concept.get('one_sentence', '')}

## 来源
对话会话 {source_session_id}

---
*由知识引擎从对话归档*
"""
                _write_file(f"wiki/concepts/{slug}.md", md)
                new_pages += 1

            return {
                "status": "ok",
                "source_session_id": source_session_id,
                "concepts_count": len(knowledge.get("concepts", [])),
                "edges_count": len(db_edges),
                "new_pages": new_pages,
            }
        except Exception as e:
            db.rollback()
            logger.error(f"对话知识归档失败 session_id={source_session_id}: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def get_graph_data(
        self,
        concept: str = None,
        depth: int = 2,
        relation_type: str = None,
    ) -> dict:
        db = SessionLocal()
        try:
            settings = get_settings()
            max_depth = min(depth, settings.knowledge_graph_max_depth)

            query = db.query(KnowledgeEdge)
            if concept:
                query = query.filter(
                    (KnowledgeEdge.source_concept == concept)
                    | (KnowledgeEdge.target_concept == concept)
                )
            if relation_type:
                query = query.filter(KnowledgeEdge.relation_type == relation_type)

            all_edges = query.all()

            if concept and max_depth > 1:
                visited = {concept}
                frontier = {concept}
                collected = list(all_edges)

                for _ in range(max_depth - 1):
                    next_frontier = set()
                    for edge in all_edges:
                        if edge.source_concept in frontier and edge.target_concept not in visited:
                            next_frontier.add(edge.target_concept)
                        if edge.target_concept in frontier and edge.source_concept not in visited:
                            next_frontier.add(edge.source_concept)
                    if not next_frontier:
                        break
                    visited.update(next_frontier)
                    frontier = next_frontier

                    extra = db.query(KnowledgeEdge).filter(
                        (KnowledgeEdge.source_concept.in_(frontier))
                        | (KnowledgeEdge.target_concept.in_(frontier))
                    ).all()
                    if relation_type:
                        extra = [e for e in extra if e.relation_type == relation_type]
                    collected.extend(extra)
                    all_edges = collected

                all_edges = collected

            nodes = set()
            links = []
            for edge in all_edges:
                nodes.add(edge.source_concept)
                nodes.add(edge.target_concept)
                links.append({
                    "source": edge.source_concept,
                    "target": edge.target_concept,
                    "relation_type": edge.relation_type,
                    "strength": edge.strength,
                    "evidence": edge.evidence,
                })

            return {
                "status": "ok",
                "nodes": list(nodes),
                "links": links,
                "total_nodes": len(nodes),
                "total_links": len(links),
            }
        except Exception as e:
            logger.error(f"获取图谱数据失败: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def get_stats(self) -> dict:
        db = SessionLocal()
        try:
            total_docs = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.is_active == True
            ).count()
            extracted_docs = db.query(KnowledgeDocument).filter(
                KnowledgeDocument.is_active == True,
                KnowledgeDocument.knowledge_extracted == True,
            ).count()
            total_edges = db.query(KnowledgeEdge).count()

            from pathlib import Path
            wiki_base = Path(get_settings().knowledge_base_path)
            wiki_pages = 0
            if wiki_base.exists():
                wiki_pages = len(list((wiki_base / "wiki").rglob("*.md")))

            concepts_count = 0
            concepts_dir = wiki_base / "wiki" / "concepts"
            if concepts_dir.exists():
                concepts_count = len(list(concepts_dir.glob("*.md")))

            orphan_concepts = self._graph_builder.find_orphan_concepts(db)
            broken_chains = self._graph_builder.find_broken_chains(db)

            return {
                "status": "ok",
                "total_documents": total_docs,
                "extracted_documents": extracted_docs,
                "total_edges": total_edges,
                "wiki_pages": wiki_pages,
                "concepts_pages": concepts_count,
                "orphan_concepts": len(orphan_concepts),
                "broken_chains": len(broken_chains),
            }
        except Exception as e:
            logger.error(f"获取知识库统计失败: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            db.close()


knowledge_engine = KnowledgeEngine()
