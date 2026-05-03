import os
import tempfile
from pathlib import Path
from app.services.obsidian_writer import ObsidianWriter, safe_filename


def test_safe_filename():
    assert safe_filename("test:file?") == "test-file-"
    assert safe_filename("a" * 150) == "a" * 100


def test_write_paper_note_creates_file(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr("app.services.obsidian_writer.get_settings",
                           lambda: type("S", (), {"obsidian_vault_path": tmpdir})())

        writer = ObsidianWriter()
        paper = {"id": "test/paper", "title": "Test Paper", "topic_id": "algorithm",
                 "authors": '["Test Author"]', "year": 2020, "subtopic": "",
                 "venue": "", "pdf_url": "http://test.pdf", "community_notes_url": "",
                 "abstract": "test abstract", "difficulty": "中等", "tags": "test",
                 "concepts": "[]"}
        path = writer.write_paper_note(paper, "")
        assert os.path.exists(path)
        content = Path(path).read_text(encoding="utf-8")
        assert content.startswith("---")
        assert "type: paper" in content
        assert "Test Paper" in content


def test_write_concept_card(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr("app.services.obsidian_writer.get_settings",
                           lambda: type("S", (), {"obsidian_vault_path": tmpdir})())

        writer = ObsidianWriter()
        concept = {"name": "Hoare Triple", "name_en": "Hoare Triple",
                   "category": "程序验证", "definition": "三元组 {P}C{Q}",
                   "one_sentence": "程序合同", "difficulty": "中等",
                   "related_concepts": ["前置条件"], "related_papers": ["test_paper"]}
        path = writer.write_concept_card(concept)
        assert os.path.exists(path)
        content = Path(path).read_text(encoding="utf-8")
        assert "type: concept" in content
        assert "Hoare Triple" in content


def test_write_dashboard(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr("app.services.obsidian_writer.get_settings",
                           lambda: type("S", (), {"obsidian_vault_path": tmpdir})())

        writer = ObsidianWriter()
        path = writer.write_dashboard()
        assert os.path.exists(path)
        content = Path(path).read_text(encoding="utf-8")
        assert "dataview" in content
        assert "01-论文精读" in content
