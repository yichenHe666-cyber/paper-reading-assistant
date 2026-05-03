#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多引擎 PDF 解析工具集 - 完全开源免费，无文件大小/页数限制
支持多种解析引擎，自动选择最佳方案

包含以下开源工具：
1. PyMuPDF (fitz) - 快速文本提取
2. PyMuPDF4LLM - 布局感知的 Markdown 转换
3. pdfplumber - 表格提取专家
4. Marker - 高质量 OCR（可选）
5. MinerU API - 云端高精度解析（可选）
"""

import os
import sys
import argparse
from pathlib import Path
from typing import Optional, List, Dict, Any
import json


class PDFParserBase:
    """PDF 解析器基类"""

    name = "base"
    description = "基础解析器"

    def __init__(self):
        self.available = False
        self._check_dependencies()

    def _check_dependencies(self):
        """检查依赖是否安装"""
        raise NotImplementedError

    def parse(self, file_path: str, **kwargs) -> Optional[str]:
        """解析 PDF 文件"""
        raise NotImplementedError

    def get_info(self) -> Dict[str, Any]:
        """获取解析器信息"""
        return {
            "name": self.name,
            "description": self.description,
            "available": self.available,
        }


class PyMuPDFParser(PDFParserBase):
    """PyMuPDF 解析器 - 快速稳定"""

    name = "pymupdf"
    description = "PyMuPDF (fitz) - 快速文本提取，适合文本型 PDF"

    def _check_dependencies(self):
        try:
            import fitz
            self.available = True
        except ImportError:
            self.available = False

    def parse(self, file_path: str, **kwargs) -> Optional[str]:
        if not self.available:
            print("❌ PyMuPDF 未安装，请运行: pip install PyMuPDF")
            return None

        import fitz

        try:
            doc = fitz.open(file_path)
            md_content = []

            md_content.append(f"# {Path(file_path).stem}\n")
            md_content.append(f"**页数**: {len(doc)}\n")
            md_content.append("---\n")

            for page_num, page in enumerate(doc, 1):
                text = page.get_text()
                if text.strip():
                    md_content.append(f"## 第 {page_num} 页\n")
                    md_content.append(text)
                    md_content.append("\n")

            doc.close()
            result = "\n".join(md_content)
            print(f"✅ PyMuPDF 解析完成 ({len(result)} 字符)")
            return result

        except Exception as e:
            print(f"❌ PyMuPDF 解析失败: {e}")
            return None


class PyMuPDF4LLMParser(PDFParserBase):
    """PyMuPDF4LLM 解析器 - 布局感知 Markdown"""

    name = "pymupdf4llm"
    description = "PyMuPDF4LLM - 布局感知的高质量 Markdown 输出"

    def _check_dependencies(self):
        try:
            from pymupdf4llm import to_markdown
            self.available = True
        except ImportError:
            self.available = False

    def parse(self, file_path: str, **kwargs) -> Optional[str]:
        if not self.available:
            print("❌ PyMuPDF4LLM 未安装，请运行: pip install pymupdf4llm")
            return None

        from pymupdf4llm import to_markdown

        try:
            page_chunks = kwargs.get("page_chunks", False)
            page_range = kwargs.get("page_range", None)

            result = to_markdown(
                file_path,
                page_chunks=page_chunks,
                pages=page_range,
                write_images=False,
            )

            if isinstance(result, list):
                result = "\n\n".join([chunk.get("text", "") for chunk in result])

            print(f"✅ PyMuPDF4LLM 解析完成 ({len(result)} 字符)")
            return result

        except Exception as e:
            print(f"❌ PyMuPDF4LLM 解析失败: {e}")
            return None


class PDFPlumberParser(PDFParserBase):
    """PDFPlumber 解析器 - 表格提取专家"""

    name = "pdfplumber"
    description = "PDFPlumber - 专注于表格和精确文本提取"

    def _check_dependencies(self):
        try:
            import pdfplumber
            self.available = True
        except ImportError:
            self.available = False

    def parse(self, file_path: str, **kwargs) -> Optional[str]:
        if not self.available:
            print("❌ PDFPlumber 未安装，请运行: pip install pdfplumber")
            return None

        import pdfplumber

        try:
            extract_tables = kwargs.get("extract_tables", True)
            md_content = []

            with pdfplumber.open(file_path) as pdf:
                md_content.append(f"# {Path(file_path).stem}\n")
                md_content.append(f"**页数**: {len(pdf.pages)}\n")
                md_content.append("---\n")

                for page_num, page in enumerate(pdf.pages, 1):
                    text = page.extract_text() or ""
                    tables = page.extract_tables() if extract_tables else []

                    has_content = text.strip() or tables
                    if not has_content:
                        continue

                    md_content.append(f"## 第 {page_num} 页\n")

                    if text.strip():
                        md_content.append(text)
                        md_content.append("\n")

                    if tables:
                        md_content.append("### 表格\n")
                        for table_idx, table in enumerate(tables, 1):
                            if table:
                                md_content.append(f"#### 表格 {table_idx}\n")
                                header = table[0] if table else []
                                rows = table[1:] if len(table) > 1 else []

                                if header:
                                    md_content.append("| " + " | ".join(
                                        [str(cell) if cell else "" for cell in header]
                                    ) + " |")
                                    md_content.append(
                                        "| " + " | ".join(["---"] * len(header)) + " |"
                                    )

                                for row in rows:
                                    md_content.append("| " + " | ".join(
                                        [str(cell) if cell else "" for cell in row]
                                    ) + " |")

                                md_content.append("\n")

            result = "\n".join(md_content)
            print(f"✅ PDFPlumber 解析完成 ({len(result)} 字符)")
            return result

        except Exception as e:
            print(f"❌ PDFPlumber 解析失败: {e}")
            return None


class MultiEnginePDFParser:
    """多引擎 PDF 解析器 - 自动选择最佳方案"""

    def __init__(self):
        self.engines: List[PDFParserBase] = [
            PyMuPDF4LLMParser(),
            PyMuPDFParser(),
            PDFPlumberParser(),
        ]
        self._log_engines_status()

    def _log_engines_status(self):
        print("\n📊 可用的 PDF 解析引擎:")
        print("-" * 60)
        for engine in self.engines:
            status = "✅ 已安装" if engine.available else "❌ 未安装"
            print(f"  {engine.name:<20} {status} - {engine.description}")
        print("-" * 60)

    def get_available_engines(self) -> List[PDFParserBase]:
        """获取所有可用的引擎"""
        return [e for e in self.engines if e.available]

    def get_best_engine(self) -> Optional[PDFParserBase]:
        """获取最佳可用引擎（按优先级）"""
        available = self.get_available_engines()
        return available[0] if available else None

    def parse(
        self,
        file_path: str,
        engine_name: Optional[str] = None,
        **kwargs
    ) -> Optional[str]:
        """
        解析 PDF 文件

        Args:
            file_path: PDF 文件路径
            engine_name: 指定引擎名称（可选），默认自动选择最佳引擎
            **kwargs: 传递给引擎的其他参数

        Returns:
            Markdown 内容或 None
        """
        if not os.path.exists(file_path):
            print(f"❌ 文件不存在: {file_path}")
            return None

        file_size = os.path.getsize(file_path)
        print(f"\n📄 文件: {Path(file_path).name}")
        print(f"📦 大小: {file_size / 1024 / 1024:.2f} MB")

        if engine_name:
            engine = next((e for e in self.engines if e.name == engine_name), None)
            if not engine:
                print(f"❌ 未找到引擎: {engine_name}")
                print(f"   可用引擎: {[e.name for e in self.get_available_engines()]}")
                return None
            if not engine.available:
                print(f"❌ 引擎 {engine_name} 未安装")
                return None
            return engine.parse(file_path, **kwargs)

        best_engine = self.get_best_engine()
        if not best_engine:
            print("❌ 没有可用的 PDF 解析引擎！")
            print("\n💡 请至少安装一个解析引擎：")
            print("  pip install pymupdf4llm      # 推荐：高质量 Markdown")
            print("  pip install PyMuPDF          # 快速文本提取")
            print("  pip install pdfplumber       # 表格提取专家")
            return None

        print(f"\n🚀 使用引擎: {best_engine.name} ({best_engine.description})")
        return best_engine.parse(file_path, **kwargs)


def save_to_file(content: str, output_path: str) -> bool:
    """保存内容到文件"""
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)
        file_size = len(content.encode("utf-8"))
        print(f"✅ 已保存到: {output_path} ({file_size / 1024:.2f} KB)")
        return True
    except Exception as e:
        print(f"❌ 保存失败: {e}")
        return False


def batch_parse(
    input_path: str,
    output_dir: str,
    engine_name: Optional[str] = None,
    **kwargs
) -> int:
    """批量解析目录中的所有 PDF"""
    parser = MultiEnginePDFParser()
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = []
    if input_path.is_file():
        if input_path.suffix.lower() == ".pdf":
            pdf_files = [input_path]
    elif input_path.is_dir():
        pdf_files = list(input_path.rglob("*.pdf"))

    if not pdf_files:
        print(f"❌ 未找到 PDF 文件: {input_path}")
        return 0

    success_count = 0
    total = len(pdf_files)

    print(f"\n📁 找到 {total} 个 PDF 文件\n")

    for idx, pdf_file in enumerate(pdf_files, 1):
        print(f"\n[{idx}/{total}] 处理: {pdf_file.name}")

        content = parser.parse(str(pdf_file), engine_name=engine_name, **kwargs)
        if content:
            output_path = output_dir / f"{pdf_file.stem}.md"
            if save_to_file(content, str(output_path)):
                success_count += 1

    print(f"\n{'='*60}")
    print(f"✅ 完成: {success_count}/{total} 个文件成功解析")
    print(f"{'='*60}\n")

    return success_count


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(
        description="🚀 多引擎 PDF 解析工具 - 开源免费，无文件大小限制",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 自动选择最佳引擎解析单个文件
  python pdf_parser.py document.pdf

  # 指定引擎解析
  python pdf_parser.py document.pdf --engine pymupdf4llm

  # 解析并保存到指定路径
  python pdf_parser.py document.pdf -o output.md

  # 批量解析整个目录
  python pdf_parser.py ./pdfs/ -o ./output/

  # 提取表格（使用 pdfplumber）
  python pdf_parser.py document.pdf --engine pdfplumber --tables

  # 显示所有可用引擎
  python pdf_parser.py --list-engines
        """,
    )

    parser.add_argument("input", nargs="?", help="PDF 文件或目录路径")
    parser.add_argument("-o", "--output", help="输出文件或目录路径")
    parser.add_argument(
        "-e", "--engine",
        choices=["pymupdf4llm", "pymupdf", "pdfplumber"],
        help="指定解析引擎（默认自动选择）"
    )
    parser.add_argument("--tables", action="store_true", help="提取表格（pdfplumber 引擎）")
    parser.add_argument("--no-tables", action="store_true", help="不提取表格")
    parser.add_argument(
        "--page-range",
        help="页码范围（如 '1-10' 或 '0'），仅部分引擎支持"
    )
    parser.add_argument(
        "--list-engines",
        action="store_true",
        help="列出所有可用引擎并退出"
    )

    args = parser.parse_args()

    if args.list_engines:
        parser_obj = MultiEnginePDFParser()
        sys.exit(0)

    if not args.input:
        parser.print_help()
        sys.exit(1)

    kwargs = {}
    if hasattr(args, "tables") and args.tables:
        kwargs["extract_tables"] = True
    if hasattr(args, "no_tables") and args.no_tables:
        kwargs["extract_tables"] = False
    if args.page_range:
        kwargs["page_range"] = args.page_range

    input_path = Path(args.input)

    if input_path.is_dir():
        output_dir = args.output or "./output/"
        success = batch_parse(
            str(input_path),
            output_dir,
            engine_name=args.engine,
            **kwargs
        )
        sys.exit(0 if success > 0 else 1)

    else:
        parser_obj = MultiEnginePDFParser()
        content = parser_obj.parse(str(input_path), engine_name=args.engine, **kwargs)

        if content:
            if args.output:
                success = save_to_file(content, args.output)
                sys.exit(0 if success else 1)
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
