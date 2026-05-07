import logging
import re
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.knowledge_edge import KnowledgeEdge

logger = logging.getLogger(__name__)


class KnowledgeGraphBuilder:

    def add_edges(self, edges: list, document_id: int, db: Session) -> list:
        created = []
        for edge_data in edges:
            source = edge_data.get("source_concept", "")
            target = edge_data.get("target_concept", "")
            relation = edge_data.get("relation_type", "")
            strength = edge_data.get("strength", 0.5)
            evidence = edge_data.get("evidence", "")

            if not source or not target or not relation:
                continue

            existing = db.query(KnowledgeEdge).filter(
                KnowledgeEdge.source_concept == source,
                KnowledgeEdge.target_concept == target,
                KnowledgeEdge.relation_type == relation,
            ).first()

            if existing:
                if strength > existing.strength:
                    existing.strength = strength
                    existing.evidence = evidence
                    if document_id is not None:
                        existing.source_document_id = document_id
                    db.flush()
                continue

            edge = KnowledgeEdge(
                source_concept=source,
                target_concept=target,
                relation_type=relation,
                strength=float(strength),
                evidence=evidence,
                source_document_id=document_id,
                is_verified=False,
            )
            db.add(edge)
            created.append(edge)

        db.flush()
        return created

    def calculate_hub_degree(self, concept: str, db: Session) -> int:
        as_source = db.query(KnowledgeEdge).filter(
            KnowledgeEdge.source_concept == concept
        ).count()
        as_target = db.query(KnowledgeEdge).filter(
            KnowledgeEdge.target_concept == concept
        ).count()
        return as_source + as_target

    def update_wiki_concept_page(self, concept_name: str, edges: list):
        settings = get_settings()
        wiki_base = Path(settings.knowledge_base_path)
        slug = _slug(concept_name)
        concept_path = wiki_base / "wiki" / "concepts" / f"{slug}.md"

        if not concept_path.exists():
            return

        try:
            current = concept_path.read_text(encoding="utf-8")
        except Exception:
            return

        related_section = "\n## 关联概念\n"
        for edge in edges:
            source = edge.get("source_concept", "")
            target = edge.get("target_concept", "")
            relation = edge.get("relation_type", "")
            strength = edge.get("strength", 0.5)
            evidence = edge.get("evidence", "")

            other = target if source == concept_name else source
            direction = "→" if source == concept_name else "←"
            related_section += f"- {direction} [[{other}]] ({relation}, 强度: {strength:.1f})"
            if evidence:
                related_section += f" — {evidence}"
            related_section += "\n"

        if "## 关联概念" in current:
            current = re.sub(
                r"## 关联概念\n.*?(?=\n## |\Z)",
                related_section.rstrip("\n"),
                current,
                flags=re.DOTALL,
            )
        else:
            current += related_section

        updated_at = f"\nupdated: {datetime.now().strftime('%Y-%m-%d')}"
        if "updated:" in current:
            current = re.sub(r"\nupdated:.*", updated_at, current)

        concept_path.write_text(current, encoding="utf-8")

    def find_orphan_concepts(self, db: Session) -> list:
        concepts_with_edges = set()
        edges = db.query(KnowledgeEdge).all()
        for edge in edges:
            concepts_with_edges.add(edge.source_concept)
            concepts_with_edges.add(edge.target_concept)

        settings = get_settings()
        wiki_base = Path(settings.knowledge_base_path)
        concepts_dir = wiki_base / "wiki" / "concepts"

        orphans = []
        if concepts_dir.exists():
            for f in concepts_dir.glob("*.md"):
                concept_name = _extract_title_from_md(f)
                if concept_name and concept_name not in concepts_with_edges:
                    orphans.append({
                        "name": concept_name,
                        "slug": f.stem,
                        "path": str(f),
                    })
        return orphans

    def find_broken_chains(self, db: Session) -> list:
        edges = db.query(KnowledgeEdge).all()

        outgoing = {}
        incoming = {}
        for edge in edges:
            outgoing.setdefault(edge.source_concept, []).append(edge)
            incoming.setdefault(edge.target_concept, []).append(edge)

        broken = []
        all_concepts = set(outgoing.keys()) | set(incoming.keys())
        for concept in all_concepts:
            has_outgoing = concept in outgoing
            has_incoming = concept in incoming
            if has_outgoing and not has_incoming:
                broken.append({
                    "concept": concept,
                    "issue": "only_outgoing",
                    "outgoing_count": len(outgoing[concept]),
                    "incoming_count": 0,
                })
            elif has_incoming and not has_outgoing:
                broken.append({
                    "concept": concept,
                    "issue": "only_incoming",
                    "outgoing_count": 0,
                    "incoming_count": len(incoming[concept]),
                })
        return broken


def _slug(text: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", text.lower())
    return re.sub(r"\s+", "-", safe).strip("-")[:60]


def _extract_title_from_md(path: Path) -> str:
    try:
        content = path.read_text(encoding="utf-8")[:500]
        m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', content, re.MULTILINE)
        if m:
            return m.group(1).strip()
        h1 = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if h1:
            return h1.group(1).strip()
    except Exception:
        pass
    return path.stem
