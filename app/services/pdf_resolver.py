import re
import time
import logging
import httpx

logger = logging.getLogger(__name__)

S2_API = "https://api.semanticscholar.org/graph/v1/paper"
UNPAYWALL_API = "https://api.unpaywall.org/v2"
CORE_API = "https://api.core.ac.uk/v3/search/works"
OPENALEX_API = "https://api.openalex.org/works"
_last_s2_request = 0.0


def _s2_rate_limit():
    global _last_s2_request
    elapsed = time.time() - _last_s2_request
    if elapsed < 1.5:
        time.sleep(1.5 - elapsed)
    _last_s2_request = time.time()


def resolve_pdf_url(title: str, current_url: str = "", doi: str = "") -> dict:
    if current_url:
        if _is_url_reachable(current_url):
            return {"pdf_url": current_url, "source": "original", "status": "ok", "doi": doi}

    if doi:
        result = _try_unpaywall(doi)
        if result:
            return result

        result = _try_openalex_by_doi(doi)
        if result:
            return result

    result = _try_semantic_scholar(title)
    if result:
        return result

    result = _try_arxiv_search(title)
    if result:
        return result

    result = _try_core(title)
    if result:
        return result

    result = _try_openalex_search(title)
    if result:
        return result

    if current_url:
        return {"pdf_url": current_url, "source": "original", "status": "unverified", "doi": doi}

    return {"pdf_url": "", "source": "none", "status": "not_found", "doi": doi}


def _is_url_reachable(url: str) -> bool:
    if not url:
        return False
    try:
        test_url = url
        if "github.com" in url and "/blob/" in url:
            test_url = url.replace("/blob/", "/raw/")
        resp = httpx.head(test_url, timeout=8, follow_redirects=True)
        return resp.status_code == 200
    except Exception:
        return False


def _try_unpaywall(doi: str) -> dict | None:
    if not doi:
        return None
    try:
        resp = httpx.get(
            f"{UNPAYWALL_API}/{doi}",
            params={"email": "openaccess@example.com"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        best_oa = data.get("best_oa_location") or {}
        oa_url = best_oa.get("url_for_pdf") or best_oa.get("url_for_landing_page") or ""

        if oa_url and _is_url_reachable(oa_url):
            resolved_doi = data.get("doi", doi)
            return {"pdf_url": oa_url, "source": "unpaywall", "status": "ok", "doi": resolved_doi}

        oa_locations = data.get("oa_locations") or []
        for loc in oa_locations:
            loc_url = loc.get("url_for_pdf") or loc.get("url_for_landing_page") or ""
            if loc_url and _is_url_reachable(loc_url):
                resolved_doi = data.get("doi", doi)
                return {"pdf_url": loc_url, "source": "unpaywall", "status": "ok", "doi": resolved_doi}

        return None
    except Exception as e:
        logger.warning(f"Unpaywall lookup failed for DOI {doi}: {e}")
        return None


def _try_semantic_scholar(title: str) -> dict | None:
    _s2_rate_limit()
    try:
        resp = httpx.get(
            f"{S2_API}/search",
            params={
                "query": title,
                "limit": 3,
                "fields": "title,openAccessPdf,externalIds",
            },
            timeout=15,
        )
        if resp.status_code == 429:
            logger.warning("Semantic Scholar rate limited")
            time.sleep(3)
            return None
        if resp.status_code != 200:
            return None

        data = resp.json()
        papers = data.get("data", [])
        if not papers:
            return None

        title_lower = title.lower().strip()
        for paper in papers:
            p_title = (paper.get("title") or "").lower().strip()
            if _title_similarity(title_lower, p_title) < 0.5:
                continue

            ext_ids = paper.get("externalIds") or {}
            doi = ext_ids.get("DOI", "")

            pdf_info = paper.get("openAccessPdf") or {}
            pdf_url = pdf_info.get("url", "") if pdf_info else ""
            if pdf_url and _is_url_reachable(pdf_url):
                return {"pdf_url": pdf_url, "source": "semantic_scholar", "status": "ok", "doi": doi}

            arxiv_id = ext_ids.get("ArXiv", "")
            if arxiv_id:
                arxiv_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                if _is_url_reachable(arxiv_url):
                    return {"pdf_url": arxiv_url, "source": "arxiv_via_s2", "status": "ok", "doi": doi}

            if doi:
                unpaywall_result = _try_unpaywall(doi)
                if unpaywall_result:
                    return unpaywall_result

        return None
    except Exception as e:
        logger.warning(f"Semantic Scholar lookup failed: {e}")
        return None


def _try_arxiv_search(title: str) -> dict | None:
    try:
        resp = httpx.get(
            "http://export.arxiv.org/api/query",
            params={"search_query": f'ti:"{title}"', "max_results": 3},
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for entry in root.findall("atom:entry", ns):
            entry_title = entry.find("atom:title", ns)
            if entry_title is None:
                continue
            title_text = entry_title.text
            if not title_text:
                continue
            entry_title_text = title_text.strip().lower().replace("\n", " ")
            if not entry_title_text:
                continue
            if _title_similarity(title.lower(), entry_title_text) < 0.4:
                continue

            for link in entry.findall("atom:link", ns):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href", "")
                    if pdf_url:
                        return {"pdf_url": pdf_url, "source": "arxiv_search", "status": "ok", "doi": ""}

            entry_id = entry.find("atom:id", ns)
            if entry_id is not None:
                arxiv_url = entry_id.text
                arxiv_id = arxiv_url.split("/abs/")[-1] if "/abs/" in arxiv_url else ""
                if arxiv_id:
                    return {"pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf", "source": "arxiv_search", "status": "ok", "doi": ""}

        return None
    except Exception as e:
        logger.warning(f"arXiv search failed: {e}")
        return None


def _try_core(title: str) -> dict | None:
    try:
        resp = httpx.get(
            CORE_API,
            params={"q": title, "limit": 3},
            timeout=15,
            headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        results = data.get("results") or []
        if not results:
            return None

        title_lower = title.lower().strip()
        for item in results:
            item_title = (item.get("title") or "").lower().strip()
            if _title_similarity(title_lower, item_title) < 0.4:
                continue

            download_url = item.get("downloadUrl") or ""
            if download_url and _is_url_reachable(download_url):
                doi = item.get("doi", "")
                return {"pdf_url": download_url, "source": "core", "status": "ok", "doi": doi}

            source_url = item.get("sourceFulltextUrls") or []
            for url in source_url:
                if url and _is_url_reachable(url):
                    doi = item.get("doi", "")
                    return {"pdf_url": url, "source": "core", "status": "ok", "doi": doi}

        return None
    except Exception as e:
        logger.warning(f"CORE lookup failed: {e}")
        return None


def _try_openalex_by_doi(doi: str) -> dict | None:
    if not doi:
        return None
    try:
        resp = httpx.get(
            f"{OPENALEX_API}/doi:{doi}",
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        oa_status = data.get("open_access", {})
        if oa_status.get("is_oa"):
            oa_url = oa_status.get("oa_url") or ""
            if oa_url and _is_url_reachable(oa_url):
                return {"pdf_url": oa_url, "source": "openalex_doi", "status": "ok", "doi": doi}

        best_oa = data.get("best_oa_location") or {}
        landing_url = best_oa.get("landing_page_url") or best_oa.get("pdf_url") or ""
        if landing_url and _is_url_reachable(landing_url):
            return {"pdf_url": landing_url, "source": "openalex_doi", "status": "ok", "doi": doi}

        return None
    except Exception as e:
        logger.warning(f"OpenAlex DOI lookup failed: {e}")
        return None


def _try_openalex_search(title: str) -> dict | None:
    try:
        resp = httpx.get(
            OPENALEX_API,
            params={"search": title, "per_page": 3},
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        results = data.get("results") or []
        if not results:
            return None

        title_lower = title.lower().strip()
        for item in results:
            item_title = (item.get("display_name") or "").lower().strip()
            if _title_similarity(title_lower, item_title) < 0.4:
                continue

            doi = item.get("doi", "")
            if doi and doi.startswith("https://doi.org/"):
                doi = doi.replace("https://doi.org/", "")

            oa_status = item.get("open_access", {})
            if oa_status.get("is_oa"):
                oa_url = oa_status.get("oa_url") or ""
                if oa_url and _is_url_reachable(oa_url):
                    return {"pdf_url": oa_url, "source": "openalex_search", "status": "ok", "doi": doi}

            best_oa = item.get("best_oa_location") or {}
            landing_url = best_oa.get("landing_page_url") or best_oa.get("pdf_url") or ""
            if landing_url and _is_url_reachable(landing_url):
                return {"pdf_url": landing_url, "source": "openalex_search", "status": "ok", "doi": doi}

            if doi:
                unpaywall_result = _try_unpaywall(doi)
                if unpaywall_result:
                    return unpaywall_result

        return None
    except Exception as e:
        logger.warning(f"OpenAlex search failed: {e}")
        return None


def _title_similarity(a: str, b: str) -> float:
    a_words = set(a.split())
    b_words = set(b.split())
    if not a_words or not b_words:
        return 0.0
    intersection = a_words & b_words
    return len(intersection) / max(len(a_words), len(b_words))


def batch_resolve_papers(papers: list[dict], delay: float = 1.5) -> list[dict]:
    results = []
    for i, paper in enumerate(papers):
        title = paper.get("title", "")
        current_url = paper.get("pdf_url", "")
        doi = paper.get("doi", "")
        logger.info(f"[{i+1}/{len(papers)}] Resolving: {title[:50]}")
        result = resolve_pdf_url(title, current_url, doi)
        results.append({
            "paper_id": paper.get("id", ""),
            "title": title,
            "old_pdf_url": current_url,
            "new_pdf_url": result["pdf_url"],
            "source": result["source"],
            "status": result["status"],
            "doi": result.get("doi", ""),
        })
        if i < len(papers) - 1:
            time.sleep(delay)
    return results
