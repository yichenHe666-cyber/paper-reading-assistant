# -*- coding: utf-8 -*-
import sqlite3
import time
import json
import httpx
from pathlib import Path
from difflib import SequenceMatcher

DB_PATH = Path("data/reading_assistant.db")
API_BASE = "https://api.openalex.org/works"
SLEEP_SECONDS = 0.1
MAX_RETRIES = 3


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def search_paper(title: str):
    for attempt in range(MAX_RETRIES):
        try:
            url = API_BASE
            params = {
                "search": title,
                "per-page": 3,
            }
            resp = httpx.get(url, params=params, timeout=8)
            if resp.status_code == 429:
                wait = 2 * (attempt + 1)
                print(f"    ⚠️ 429 限流，等待 {wait}s 后重试...")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                print(f"    ⚠️ HTTP {resp.status_code}")
                return None
            data = resp.json()
            papers = data.get("results", [])
            if not papers:
                return None

            best = None
            best_score = 0.0
            for p in papers:
                score = similarity(title, p.get("display_name", ""))
                if score > best_score:
                    best_score = score
                    best = p

            if best and best_score >= 0.5:
                return best
            return None
        except Exception as e:
            print(f"    API error: {e}")
            time.sleep(1)
    return None


def extract_authors(paper_data: dict):
    authorships = paper_data.get("authorships", [])
    if not authorships:
        return None
    names = []
    for a in authorships:
        author_info = a.get("author", {})
        name = author_info.get("display_name", "").strip()
        if name:
            names.append(name)
    return names if names else None


def extract_doi(paper_data: dict) -> str:
    doi = paper_data.get("doi", "")
    if doi and doi.startswith("https://doi.org/"):
        doi = doi.replace("https://doi.org/", "")
    return doi


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM papers")
    total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM papers WHERE authors IS NULL OR authors = '' OR authors = '[]' OR authors = '[\"Unknown\"]'")
    before_missing_authors = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM papers WHERE year IS NULL")
    before_missing_year = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM papers WHERE doi IS NULL OR doi = ''")
    before_missing_doi = cursor.fetchone()[0]

    print(f"【修复前】总论文: {total}")
    print(f"  缺失作者: {before_missing_authors} ({before_missing_authors/total*100:.1f}%)")
    print(f"  缺失年份: {before_missing_year} ({before_missing_year/total*100:.1f}%)")
    print(f"  缺失DOI: {before_missing_doi} ({before_missing_doi/total*100:.1f}%)")
    print()

    cursor.execute('''
        SELECT id, title, authors, year, doi
        FROM papers
        WHERE authors IS NULL OR authors = '' OR authors = '[]' OR authors = '["Unknown"]'
           OR year IS NULL
           OR doi IS NULL OR doi = ''
        ORDER BY topic_id
    ''')
    to_fix = cursor.fetchall()
    print(f"待修复论文数: {len(to_fix)}")
    print("=" * 60)

    fixed_authors = 0
    fixed_year = 0
    fixed_doi = 0
    fixed_any = 0
    failed = []

    for idx, row in enumerate(to_fix, 1):
        paper_id = row["id"]
        title = row["title"]
        current_authors = row["authors"]
        current_year = row["year"]
        current_doi = row["doi"] if "doi" in row.keys() else ""

        need_authors = current_authors is None or current_authors in ("", "[]", '["Unknown"]')
        need_year = current_year is None
        need_doi = not current_doi

        print(f"[{idx}/{len(to_fix)}] {title[:60]}...")

        result = search_paper(title)
        time.sleep(SLEEP_SECONDS)

        if not result:
            print(f"  → 未找到匹配")
            failed.append({"id": paper_id, "title": title, "reason": "OpenAlex 无匹配结果"})
            continue

        match_score = similarity(title, result.get("display_name", ""))
        print(f"  → 匹配: '{result.get('display_name', '')[:60]}...' (相似度 {match_score:.2f})")

        updated = False

        if need_authors:
            new_authors = extract_authors(result)
            if new_authors:
                authors_json = json.dumps(new_authors, ensure_ascii=False)
                cursor.execute(
                    "UPDATE papers SET authors = ? WHERE id = ?",
                    (authors_json, paper_id)
                )
                fixed_authors += 1
                updated = True
                print(f"    ✓ 作者: {', '.join(new_authors[:3])}{'...' if len(new_authors) > 3 else ''}")

        if need_year:
            new_year = result.get("publication_year")
            if new_year:
                cursor.execute(
                    "UPDATE papers SET year = ? WHERE id = ?",
                    (int(new_year), paper_id)
                )
                fixed_year += 1
                updated = True
                print(f"    ✓ 年份: {new_year}")

        if need_doi:
            new_doi = extract_doi(result)
            if new_doi:
                cursor.execute(
                    "UPDATE papers SET doi = ? WHERE id = ?",
                    (new_doi, paper_id)
                )
                fixed_doi += 1
                updated = True
                print(f"    ✓ DOI: {new_doi}")

        if updated:
            fixed_any += 1
            conn.commit()
        else:
            failed.append({"id": paper_id, "title": title, "reason": "API 返回结果中仍无有效数据"})
            print(f"    ✗ API 结果中仍无有效数据")

    cursor.execute("SELECT COUNT(*) FROM papers WHERE authors IS NULL OR authors = '' OR authors = '[]' OR authors = '[\"Unknown\"]'")
    after_missing_authors = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM papers WHERE year IS NULL")
    after_missing_year = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM papers WHERE doi IS NULL OR doi = ''")
    after_missing_doi = cursor.fetchone()[0]

    print()
    print("=" * 60)
    print("【修复完成】")
    print(f"  成功修复作者: {fixed_authors} 篇")
    print(f"  成功修复年份: {fixed_year} 篇")
    print(f"  成功修复DOI: {fixed_doi} 篇")
    print(f"  至少修复一项: {fixed_any} 篇")
    print(f"  修复失败: {len(failed)} 篇")
    print()
    print("【修复后】")
    print(f"  缺失作者: {after_missing_authors} ({after_missing_authors/total*100:.1f}%)")
    print(f"  缺失年份: {after_missing_year} ({after_missing_year/total*100:.1f}%)")
    print(f"  缺失DOI: {after_missing_doi} ({after_missing_doi/total*100:.1f}%)")
    print(f"  作者修复率: {(before_missing_authors - after_missing_authors) / max(before_missing_authors, 1) * 100:.1f}%")
    print(f"  年份修复率: {(before_missing_year - after_missing_year) / max(before_missing_year, 1) * 100:.1f}%")
    print(f"  DOI修复率: {(before_missing_doi - after_missing_doi) / max(before_missing_doi, 1) * 100:.1f}%")

    if failed:
        fail_path = Path("data/failed_enrichment_log.json")
        with open(fail_path, "w", encoding="utf-8") as f:
            json.dump(failed, f, ensure_ascii=False, indent=2)
        print(f"\n未成功修复清单已保存: {fail_path}")

    conn.close()


if __name__ == "__main__":
    main()
