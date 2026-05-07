from dataclasses import dataclass, field


@dataclass
class ParsedDocument:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    content: str = ""
    sections: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    raw_path: str = ""
    parse_status: str = "success"
    parse_errors: list[str] = field(default_factory=list)
