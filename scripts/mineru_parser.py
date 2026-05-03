#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MinerU 文档解析工具 - Agent Lightweight API 封装
基于 OpenDataLab MinerU 开源项目，支持 PDF、图片、Word、PPT 等文档格式转换为 Markdown

GitHub: https://github.com/opendatalab/MinerU
文档: https://mineru.net/doc/docs/index_en/
"""

import requests
import time
import sys
import os
from pathlib import Path
from typing import Optional, Dict, Any


BASE_URL = "https://mineru.net/api/v1/agent"


def parse_by_url(
    url: str,
    language: str = "ch",
    page_range: Optional[str] = None,
    enable_table: bool = True,
    is_ocr: bool = False,
    enable_formula: bool = True,
    timeout: int = 300,
    interval: int = 3,
) -> Optional[str]:
    """
    通过 URL 提交文档解析任务并等待结果

    Args:
        url: 远程文件 URL（支持 PDF、图片、Doc/Docx、PPT/PPTx）
        language: 文档语言，默认 ch（中文），可选 en/japan/korean 等
        page_range: 页码范围，仅对 PDF 有效，如 "1-10" 或 "5"
        enable_table: 是否启用表格识别，默认 True，仅对 PDF 有效
        is_ocr: 是否启用 OCR，默认 False，仅对 PDF 有效
        enable_formula: 是否启用公式识别，默认 True，仅对 PDF 有效
        timeout: 超时时间（秒），默认 300
        interval: 轮询间隔（秒），默认 3

    Returns:
        Markdown 格式的文档内容，失败返回 None
    """
    data = {
        "url": url,
        "language": language,
        "enable_table": enable_table,
        "is_ocr": is_ocr,
        "enable_formula": enable_formula,
    }
    if page_range:
        data["page_range"] = page_range

    try:
        resp = requests.post(f"{BASE_URL}/parse/url", json=data, timeout=30)
        result = resp.json()
        if result["code"] != 0:
            print(f"❌ 提交失败: {result['msg']}")
            return None

        task_id = result["data"]["task_id"]
        print(f"✅ 任务已提交, task_id: {task_id}")

        return _poll_result(task_id, timeout=timeout, interval=interval)

    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return None


def parse_by_file(
    file_path: str,
    language: str = "ch",
    page_range: Optional[str] = None,
    enable_table: bool = True,
    is_ocr: bool = False,
    enable_formula: bool = True,
    timeout: int = 300,
    interval: int = 3,
) -> Optional[str]:
    """
    通过本地文件上传提交文档解析任务并等待结果

    Args:
        file_path: 本地文件路径（支持 PDF、图片、Docx、PPTx、xls/xlsx）
        language: 文档语言，默认 ch
        page_range: 页码范围，仅对 PDF 有效
        enable_table: 是否启用表格识别
        is_ocr: 是否启用 OCR
        enable_formula: 是否启用公式识别
        timeout: 超时时间（秒）
        interval: 轮询间隔（秒）

    Returns:
        Markdown 格式的文档内容，失败返回 None
    """
    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return None

    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)

    if file_size > 10 * 1024 * 1024:
        print(f"❌ 文件大小超过限制 (10MB): {file_size / 1024 / 1024:.2f}MB")
        print("💡 提示: 请使用 Precision Extract API (需要 Token)")
        return None

    data = {
        "file_name": file_name,
        "language": language,
        "enable_table": enable_table,
        "is_ocr": is_ocr,
        "enable_formula": enable_formula,
    }
    if page_range:
        data["page_range"] = page_range

    try:
        print(f"📤 正在上传文件: {file_name} ({file_size / 1024 / 1024:.2f}MB)")

        resp = requests.post(f"{BASE_URL}/parse/file", json=data, timeout=30)
        result = resp.json()

        if result["code"] != 0:
            print(f"❌ 获取上传 URL 失败: {result['msg']}")
            return None

        task_id = result["data"]["task_id"]
        file_url = result["data"]["file_url"]
        print(f"✅ 任务已创建, task_id: {task_id}")

        with open(file_path, "rb") as f:
            put_resp = requests.put(file_url, data=f, timeout=60)
            if put_resp.status_code not in (200, 201):
                print(f"❌ 文件上传失败, HTTP {put_resp.status_code}")
                return None

        print("✅ 文件上传成功, 等待解析...")
        return _poll_result(task_id, timeout=timeout, interval=interval)

    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return None


def _poll_result(task_id: str, timeout: int = 300, interval: int = 3) -> Optional[str]:
    """
    轮询查询解析结果

    Args:
        task_id: 任务 ID
        timeout: 超时时间（秒）
        interval: 轮询间隔（秒）

    Returns:
        Markdown 内容或 None
    """
    state_labels = {
        "uploading": "⬇️ 下载文件中",
        "pending": "⏳ 排队等待中",
        "running": "🔄 解析处理中",
        "waiting-file": "📁 等待文件上传",
    }

    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{BASE_URL}/parse/{task_id}", timeout=30)
            result = resp.json()
            state = result["data"]["state"]
            elapsed = int(time.time() - start)

            if state == "done":
                markdown_url = result["data"]["markdown_url"]
                print(f"✅ 解析完成 ({elapsed}s), 正在下载 Markdown...")

                md_resp = requests.get(markdown_url, timeout=60)
                content = md_resp.text
                print(f"✅ 成功获取文档内容 ({len(content)} 字符)")
                return content

            if state == "failed":
                err_msg = result["data"].get("err_msg", "未知错误")
                err_code = result["data"].get("err_code", "")
                print(f"❌ 解析失败 ({elapsed}s): [{err_code}] {err_msg}")
                return None

            status_text = state_labels.get(state, state)
            print(f"[{elapsed}s] {status_text}...")
            time.sleep(interval)

        except Exception as e:
            print(f"⚠️ 查询异常: {e}, 继续重试...")
            time.sleep(interval)

    print(f"⏰ 轮询超时 ({timeout}s), 请手动查询 task_id: {task_id}")
    return None


def save_to_file(content: str, output_path: str) -> bool:
    """
    将 Markdown 内容保存到文件

    Args:
        content: Markdown 内容
        output_path: 输出文件路径

    Returns:
        是否保存成功
    """
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ 已保存到: {output_path}")
        return True
    except Exception as e:
        print(f"❌ 保存失败: {e}")
        return False


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="MinerU 文档解析工具 - 将 PDF/图片/Word/PPT 转换为 Markdown",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 解析远程 URL
  python mineru_parser.py --url https://example.com/document.pdf

  # 解析本地文件
  python mineru_parser.py --file document.pdf

  # 解析并保存到指定路径
  python mineru_parser.py --file document.pdf --output result.md

  # 指定页码范围和语言
  python mineru_parser.py --file document.pdf --page-range 1-10 --language en

  # 启用 OCR（适用于扫描件）
  python mineru_parser.py --file scanned.pdf --ocr
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", "-u", help="远程文件 URL")
    group.add_argument("--file", "-f", help="本地文件路径")

    parser.add_argument("--output", "-o", help="输出文件路径（可选，默认打印到控制台）")
    parser.add_argument("--language", "-l", default="ch", help="文档语言 (ch/en/japan等, 默认 ch)")
    parser.add_argument("--page-range", "-p", help="页码范围 (如 1-10 或 5, 仅PDF有效)")
    parser.add_argument("--no-table", action="store_true", help="禁用表格识别")
    parser.add_argument("--ocr", action="store_true", help="启用 OCR (适用于扫描件)")
    parser.add_argument("--no-formula", action="store_true", help="禁用公式识别")
    parser.add_argument("--timeout", type=int, default=300, help="超时时间(秒, 默认300)")
    parser.add_argument("--interval", type=int, default=3, help="轮询间隔(秒, 默认3)")

    args = parser.parse_args()

    kwargs = {
        "language": args.language,
        "page_range": args.page_range,
        "enable_table": not args.no_table,
        "is_ocr": args.ocr,
        "enable_formula": not args.no_formula,
        "timeout": args.timeout,
        "interval": args.interval,
    }

    if args.url:
        content = parse_by_url(args.url, **kwargs)
    else:
        content = parse_by_file(args.file, **kwargs)

    if content:
        if args.output:
            save_to_file(content, args.output)
        else:
            print("\n" + "=" * 80)
            print("📄 文档内容 (Markdown):")
            print("=" * 80 + "\n")
            print(content)
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
