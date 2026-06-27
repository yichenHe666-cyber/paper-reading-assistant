from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.services.llm_navigator import generate_reading_navigator
from app.services.llm_drafter import generate_note_draft
from app.services.llm_concept_mapper import generate_concept_cards
from app.services.llm_vocabulary import extract_vocabulary, apply_dedup, build_vocabulary_markdown
from app.services.academic_reading_engine import analyze_first_pass
from app.services.formal_deconstructor import deconstruct_formal_content
from app.services.critical_reviewer import review_critically
from app.services.smart_note_synthesizer import synthesize_note
from app.services.pdf_fetcher import get_paper_text
from app.services.cost_tracker import check_budget, record_cost, requires_approval
from app.services.llm_cache import get_cache, set_cache
from app.models.paper import Paper

router = APIRouter()


def _get_paper_dict(db, paper_id: str) -> dict:
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")
    return {
        "id": paper.id,
        "title": paper.title,
        "authors": paper.authors,
        "year": paper.year,
        "topic_id": paper.topic_id,
        "subtopic": paper.subtopic,
        "venue": paper.venue,
        "pdf_url": paper.pdf_url,
        "community_notes_url": paper.community_notes_url,
        "abstract": paper.abstract,
        "difficulty": paper.difficulty,
        "tags": paper.tags,
        "doi": paper.doi,
        "concepts": paper.concepts,
    }


# ── Backward-compatible endpoints (delegate to old modules) ──

@router.post("/navigator")
def get_navigator(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    force = data.get("force", False)
    paper = _get_paper_dict(db, paper_id)

    if not force:
        cached = get_cache(db, paper_id, "navigator")
        if cached:
            return {"navigator": cached, "from_cache": True}

    estimated_cost = 0.003
    if not check_budget(db, estimated_cost):
        return {"error": "⚠️ 今日 LLM 预算已用完，请明天再试"}

    try:
        result, usage = generate_reading_navigator(paper)
        set_cache(db, paper_id, "navigator", result, usage.get("total_tokens", 0))
        record_cost(db, "reading_nav", usage["model"], usage["prompt_tokens"], usage["completion_tokens"], paper_id)
        return {"navigator": result, "from_cache": False}
    except Exception as e:
        return {"error": f"LLM 调用失败: {str(e)}"}


@router.post("/note-draft")
def get_note_draft(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    navigator = data.get("navigator", {})
    force = data.get("force", False)
    paper = _get_paper_dict(db, paper_id)

    if not force:
        cached = get_cache(db, paper_id, "note_draft")
        if cached:
            return {"note_draft": cached, "from_cache": True}

    estimated_cost = 0.005
    if not check_budget(db, estimated_cost):
        return {"error": "⚠️ 今日 LLM 预算已用完"}

    try:
        result, usage = generate_note_draft(paper, navigator)
        set_cache(db, paper_id, "note_draft", result, usage.get("total_tokens", 0))
        record_cost(db, "note_draft", usage["model"], usage["prompt_tokens"], usage["completion_tokens"], paper_id)
        return {"note_draft": result, "from_cache": False}
    except Exception as e:
        return {"error": f"LLM 调用失败: {str(e)}"}


@router.post("/concept-cards")
def get_concept_cards(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    navigator = data.get("navigator", {})
    force = data.get("force", False)
    paper = _get_paper_dict(db, paper_id)

    if not force:
        cached = get_cache(db, paper_id, "concept_cards")
        if cached:
            return {"concept_cards": cached, "from_cache": True}

    estimated_cost = 0.003
    if not check_budget(db, estimated_cost):
        return {"error": "⚠️ 今日 LLM 预算已用完"}

    try:
        result, usage = generate_concept_cards(paper, navigator)
        set_cache(db, paper_id, "concept_cards", result, usage.get("total_tokens", 0))
        record_cost(db, "concept_map", usage["model"], usage["prompt_tokens"], usage["completion_tokens"], paper_id)
        return {"concept_cards": result, "from_cache": False}
    except Exception as e:
        return {"error": f"LLM 调用失败: {str(e)}"}


@router.post("/vocabulary")
def get_vocabulary(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    force = data.get("force", False)
    paper = _get_paper_dict(db, paper_id)

    if not force:
        cached = get_cache(db, paper_id, "vocabulary")
        if cached:
            return {"vocabulary": cached.get("vocabulary"), "vocabulary_md": cached.get("vocabulary_md"), "from_cache": True}

    estimated_cost = 0.003
    if not check_budget(db, estimated_cost):
        return {"error": "⚠️ 今日 LLM 预算已用完"}

    try:
        raw_words, usage = extract_vocabulary(paper)
        record_cost(db, "vocabulary", usage["model"], usage["prompt_tokens"], usage["completion_tokens"], paper_id)
        deduped = apply_dedup(db, paper_id, raw_words)
        from datetime import date
        paper["_now"] = str(date.today())
        vocab_md = build_vocabulary_markdown(paper, deduped)
        result = {"vocabulary": deduped, "vocabulary_md": vocab_md}
        set_cache(db, paper_id, "vocabulary", result, usage.get("total_tokens", 0))
        return {"vocabulary": deduped, "vocabulary_md": vocab_md, "from_cache": False}
    except Exception as e:
        return {"error": f"LLM 调用失败: {str(e)}"}


# ── New academic reading pipeline ──

@router.post("/one-click")
def one_click_generate(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    reading_round = data.get("reading_round", "R1")
    force = data.get("force", False)
    paper = _get_paper_dict(db, paper_id)

    results = {"paper_id": paper_id, "reading_round": reading_round, "from_cache": []}
    errors = []
    cached_types = []

    def _get_or_generate(cache_key, generate_fn, cost_label, *gen_args):
        if not force:
            cached = get_cache(db, paper_id, cache_key)
            if cached:
                cached_types.append(cache_key)
                return cached, None
        estimated_cost = 0.004
        if not check_budget(db, estimated_cost):
            errors.append(f"{cache_key}: 预算已用完")
            return None, None
        try:
            content, usage = generate_fn(*gen_args)
            if content:
                set_cache(db, paper_id, cache_key, content, usage.get("total_tokens", 0) if usage else 0)
                if usage:
                    record_cost(db, cost_label, usage["model"],
                                usage.get("prompt_tokens", 0),
                                usage.get("completion_tokens", 0), paper_id)
            return content, usage
        except Exception as e:
            errors.append(f"{cache_key}: {e}")
            return None, None

    # ── R1: First pass + vocabulary ──
    first_pass, _ = _get_or_generate("R1_first_pass", lambda: analyze_first_pass(paper), "R1_first_pass")
    if first_pass:
        results["first_pass"] = first_pass

    vocab, _ = _get_or_generate("vocabulary", lambda: extract_vocabulary(paper), "vocabulary")
    if vocab:
        deduped = apply_dedup(db, paper_id, vocab)
        from datetime import date
        paper["_now"] = str(date.today())
        vocab_md = build_vocabulary_markdown(paper, deduped)
        results["vocabulary"] = deduped
        results["vocabulary_md"] = vocab_md

    if reading_round in ("R1",):
        if cached_types:
            results["from_cache"] = cached_types
        if errors:
            results["errors"] = errors
        return results

    # ── R2: Formal deconstruction + critical review ──
    paper_text = get_paper_text(paper_id)
    if not paper_text:
        errors.append("formal_decon: 无可用论文文本，请先下载PDF提取文本")

    formal_decon, _ = _get_or_generate(
        "R2_formal_decon",
        lambda: deconstruct_formal_content(paper_text),
        "R2_formal_decon"
    )
    if formal_decon:
        results["formal_decon"] = formal_decon

    if first_pass:
        critical_rev, _ = _get_or_generate(
            "R2_critical_review",
            lambda: review_critically(paper_text, first_pass, db),
            "R2_critical_review"
        )
        if critical_rev:
            results["critical_review"] = critical_rev
    else:
        errors.append("critical_review: 缺少第一遍分析输出")

    if reading_round in ("R2",):
        if cached_types:
            results["from_cache"] = cached_types
        if errors:
            results["errors"] = errors
        return results

    # ── R3: Smart note synthesis ──
    if first_pass and formal_decon:
        cr_for_synthesis = critical_rev if "critical_review" in results else {"findings": [], "cross_paper_findings": []}
        note, usage_note = _get_or_generate(
            "R3_smart_note",
            lambda: synthesize_note(paper, first_pass, formal_decon, cr_for_synthesis, paper_text),
            "R3_smart_note"
        )
        if note:
            results["note_draft"] = note
            if isinstance(note, str):
                results["navigator"] = first_pass
                five_c = first_pass.get("5c_summary", {})
                if isinstance(five_c, dict):
                    results["concept_cards"] = [
                        {"name": k, "name_en": k, "definition": str(v), "category": "5C",
                         "related_concepts": [], "related_papers": [], "difficulty": "中等",
                         "context_in_paper": "", "evolution_line": "", "one_sentence": str(v),
                         "formal_definition": str(v)}
                        for k, v in five_c.items()
                    ]
                else:
                    results["concept_cards"] = []
            try:
                import threading
                from app.services.memory_distiller import memory_distiller
                reading_result_for_distill = {
                    "paper": paper,
                    "r1_output": first_pass,
                    "r2_formal": formal_decon,
                    "r2_critical": cr_for_synthesis,
                    "r3_note": note if isinstance(note, str) else str(note),
                }
                def _distill_and_observe(pid, rr):
                    from app.database.session import SessionLocal
                    db_local = SessionLocal()
                    try:
                        memory_distiller.distill_reading_session(pid, rr)
                    except Exception:
                        pass
                    try:
                        from app.services.memory_observer import memory_observer
                        memory_observer.run_consolidation_cycle(db_local)
                    except Exception:
                        pass
                    finally:
                        db_local.close()

                t = threading.Thread(
                    target=_distill_and_observe,
                    args=(paper_id, reading_result_for_distill),
                    daemon=True,
                )
                t.start()
                results["_distill_triggered"] = True
            except Exception:
                pass
    else:
        errors.append("smart_note: 缺少 R1/R2 输出")

    if cached_types:
        results["from_cache"] = cached_types
    if errors:
        results["errors"] = errors
    return results


# ── First-pass only endpoint (for incremental generation) ──

@router.post("/first-pass")
def get_first_pass(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    force = data.get("force", False)
    paper = _get_paper_dict(db, paper_id)

    if not force:
        cached = get_cache(db, paper_id, "R1_first_pass")
        if cached:
            return {"first_pass": cached, "from_cache": True}

    estimated_cost = 0.004
    if not check_budget(db, estimated_cost):
        return {"error": "⚠️ 今日 LLM 预算已用完"}

    try:
        result, usage = analyze_first_pass(paper)
        set_cache(db, paper_id, "R1_first_pass", result, usage.get("total_tokens", 0))
        record_cost(db, "R1_first_pass", usage["model"], usage["prompt_tokens"], usage["completion_tokens"], paper_id)
        return {"first_pass": result, "from_cache": False}
    except Exception as e:
        return {"error": f"第一遍分析失败: {str(e)}"}


# ── Existing endpoints preserved ──

@router.post("/recommend")
def recommend_next(data: dict, db: Session = Depends(get_db)):
    topic_id = data.get("topic_id")
    exclude_id = data.get("exclude_id")
    q = db.query(Paper).filter(Paper.read_status == "未读")
    if topic_id:
        q = q.filter(Paper.topic_id == topic_id)
    if exclude_id:
        q = q.filter(Paper.id != exclude_id)
    paper = q.order_by(Paper.year.desc()).first()
    if paper:
        return {
            "id": paper.id,
            "title": paper.title,
            "authors": paper.authors,
            "year": paper.year,
            "topic_id": paper.topic_id,
        }
    return {"message": "该主题下没有更多未读论文了，试试换一个主题！"}


@router.post("/download-pdf")
def download_paper_pdf(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    if not paper_id:
        raise HTTPException(status_code=400, detail="paper_id is required")
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    if not paper.pdf_url:
        from app.services.pdf_resolver import resolve_pdf_url
        resolved = resolve_pdf_url(paper.title, "", paper.doi or "")
        if resolved.get("pdf_url"):
            paper.pdf_url = resolved["pdf_url"]
            if resolved.get("doi") and not paper.doi:
                paper.doi = resolved["doi"]
            db.commit()
        else:
            return {"error": "该论文没有 PDF 链接，且无法自动查找可用来源"}

    from app.services.pdf_fetcher import download_pdf
    result = download_pdf(paper_id, paper.pdf_url)

    if result.get("status") == "text_extracted":
        text = get_paper_text(paper_id)
        if text and len(text) > 100:
            paper.abstract = text[:2000]
            db.commit()

    return result


@router.post("/resolve-pdf")
def resolve_paper_pdf(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id")
    if not paper_id:
        raise HTTPException(status_code=400, detail="paper_id is required")
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    from app.services.pdf_resolver import resolve_pdf_url
    result = resolve_pdf_url(paper.title, paper.pdf_url or "", paper.doi or "")

    if result.get("pdf_url") and result["pdf_url"] != paper.pdf_url:
        paper.pdf_url = result["pdf_url"]
    if result.get("doi") and not paper.doi:
        paper.doi = result["doi"]
    db.commit()

    return {
        "paper_id": paper_id,
        "title": paper.title,
        "pdf_url": result.get("pdf_url", ""),
        "source": result.get("source", ""),
        "status": result.get("status", ""),
        "doi": result.get("doi", ""),
    }


@router.post("/batch-resolve-pdfs")
def batch_resolve_pdfs(data: dict, db: Session = Depends(get_db)):
    topic_id = data.get("topic_id")
    limit = data.get("limit", 20)

    q = db.query(Paper)
    if topic_id:
        q = q.filter(Paper.topic_id == topic_id)
    papers = q.limit(limit).all()

    if not papers:
        return {"error": "没有找到论文"}

    paper_dicts = [{"id": p.id, "title": p.title, "pdf_url": p.pdf_url or "", "doi": p.doi or ""} for p in papers]

    from app.services.pdf_resolver import batch_resolve_papers
    results = batch_resolve_papers(paper_dicts)

    updated = 0
    for r in results:
        if r["new_pdf_url"] and r["new_pdf_url"] != r["old_pdf_url"]:
            paper = db.query(Paper).filter(Paper.id == r["paper_id"]).first()
            if paper:
                paper.pdf_url = r["new_pdf_url"]
                updated += 1
        if r.get("doi"):
            paper = db.query(Paper).filter(Paper.id == r["paper_id"]).first()
            if paper and not paper.doi:
                paper.doi = r["doi"]
    db.commit()

    return {
        "total": len(results),
        "updated": updated,
        "results": results,
    }


@router.post("/proxy-pdf")
def proxy_pdf(data: dict, db: Session = Depends(get_db)):
    paper_id = data.get("paper_id", "")
    if not paper_id:
        raise HTTPException(status_code=400, detail="paper_id is required")

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    import re as _re
    from app.services.pdf_fetcher import RAW_DIR

    slug = _re.sub(r'[<>:"/\\|?*]', '-', paper_id)[:80]
    local_pdf = RAW_DIR / f"{slug}.pdf"

    if local_pdf.exists():
        pdf_bytes = local_pdf.read_bytes()
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename={slug}.pdf",
                "Content-Length": str(len(pdf_bytes)),
                "Cache-Control": "public, max-age=86400",
            },
        )

    if not paper.pdf_url:
        raise HTTPException(status_code=404, detail="没有 PDF 链接")

    import httpx
    url = paper.pdf_url
    if "github.com" in url and "/blob/" in url:
        url = url.replace("/blob/", "/raw/")

    try:
        resp = httpx.get(url, timeout=60, follow_redirects=True)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"PDF 源返回 {resp.status_code}")

        content_type = resp.headers.get("content-type", "")
        if "pdf" not in content_type.lower() or len(resp.content) > 50 * 1024 * 1024:
            raise HTTPException(status_code=502, detail="PDF 源返回非 PDF 或文件过大")

        RAW_DIR.mkdir(parents=True, exist_ok=True)
        local_pdf.write_bytes(resp.content)

        return Response(
            content=resp.content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename={slug}.pdf",
                "Content-Length": str(len(resp.content)),
                "Cache-Control": "public, max-age=86400",
            },
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="PDF 下载超时")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"PDF 获取失败: {e}")


@router.post("/upload-pdf")
def upload_paper_pdf(
    paper_id: str = Form(""),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
):
    if not paper_id:
        raise HTTPException(status_code=400, detail="paper_id is required")
    if not file:
        raise HTTPException(status_code=400, detail="file is required")

    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="论文不存在")

    file_bytes = file.file.read()
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="PDF 文件大小超过 50MB 限制")

    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="上传文件不是有效的 PDF 格式")

    from app.services.pdf_fetcher import save_uploaded_pdf
    result = save_uploaded_pdf(paper_id, file_bytes)

    if result.get("status") in ("text_extracted", "pdf_saved", "extraction_empty"):
        paper.pdf_url = f"local://uploaded/{paper_id}"
        db.commit()

    return {
        "paper_id": paper_id,
        "status": result.get("status"),
        "pdf_size_kb": result.get("pdf_size_kb"),
        "text_length": result.get("text_length"),
        "error": result.get("error"),
        "note": result.get("note"),
    }
