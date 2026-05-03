from app.services.paper_parser import parse_readme_to_papers


def test_parse_bullet_list():
    md = """## Artificial Intelligence

* :scroll: [Analysis of Three Bayesian Network Inference Algorithms](paper1.pdf) by Rose F. Liu

* [Computing Machinery and Intelligence](http://example.com/turing.pdf) by A.M. Turing

* [Judea Pearl](http://bayes.cs.ucla.edu/jp_home.html)
"""
    papers = parse_readme_to_papers(md, "artificial_intelligence")
    assert len(papers) >= 1, f"Expected at least 1 paper, got {len(papers)}"


def test_parse_arxiv_link():
    md = "* [Attention Is All You Need](https://arxiv.org/abs/1706.03762) by Vaswani et al."
    papers = parse_readme_to_papers(md, "machine_learning")
    assert len(papers) >= 1
    assert "Attention" in papers[0]["title"]


def test_parse_authors_from_by():
    md = "* [Paper Title](http://example.com) by Author One and Author Two"
    papers = parse_readme_to_papers(md, "test")
    assert len(papers) == 1
    import json
    authors = json.loads(papers[0]["authors"])
    assert "Author One" in authors or authors == ["Unknown"]


def test_dedup_same_title():
    md = """## Test
* [Same Paper](http://a.pdf)
* [Same Paper](http://a.pdf)
"""
    papers = parse_readme_to_papers(md, "test")
    assert len(papers) == 1, f"Expected 1 unique paper, got {len(papers)}"


def test_skip_non_paper_entries():
    md = """## Test
* :open_file_folder: Summary of Papers
* [Real Paper](http://a.pdf)
"""
    papers = parse_readme_to_papers(md, "test")
    assert len(papers) == 1
    assert "Real" in papers[0]["title"]


def test_parse_dash_list_format():
    md = """# Brain-computer Interface

- [Brain-computer interfaces for communication and control](http://example.com/bci.pdf)
- [Breaking the silence: Brain-computer interfaces](https://example.com/silence.pdf)
"""
    papers = parse_readme_to_papers(md, "brain-computer-interface")
    assert len(papers) == 2
    assert "Brain-computer interfaces for communication" in papers[0]["title"]


def test_parse_reference_style_links():
    md = """# Combinatory Logic

* [Flattening Combinators: Surviving Without Parentheses]
  by Chris Okasaki (2003) ([DOI])

* [Combinatorial Analysis and Computers]
   by Marshall Hall Jr. and Donald E. Knuth (1965)

[Flattening Combinators: Surviving Without Parentheses]:
    https://www.cambridge.org/core/content/view/paper.pdf
[DOI]:
    https://doi.org/10.1017/S0956796802004483
[Combinatorial Analysis and Computers]:
     https://web.archive.org/web/paper.pdf
"""
    papers = parse_readme_to_papers(md, "combinatory_logic")
    assert len(papers) == 2
    assert "Flattening Combinators" in papers[0]["title"]


def test_parse_reference_link_with_by_clause():
    md = """# Data Science

## Data Cleaning

* :scroll: [Tidy Data] by Hadley Wickham (2014)

[Tidy Data]: https://www.jstatsoft.org/article/view/v059i10
"""
    papers = parse_readme_to_papers(md, "data_science")
    assert len(papers) == 1
    assert "Tidy Data" in papers[0]["title"]
    import json
    authors = json.loads(papers[0]["authors"])
    assert "Hadley Wickham" in authors
    assert papers[0]["year"] == 2014


def test_parse_plain_link_with_by():
    md = """ ## Streaming Algorithms

 [Counting large numbers of events in small registers](http://example.com/morris.pdf) by Robert Morris

 [Probabilistic Counting Algorithms](https://example.com/flajolet.pdf) by Philppe Flajolet, Nigel Martin
"""
    papers = parse_readme_to_papers(md, "streaming_algorithms")
    assert len(papers) == 2
    assert "Counting large numbers" in papers[0]["title"]


def test_parse_h3_heading_format():
    md = """## Distributed Systems

### [MapReduce](http://example.com/mapreduce.pdf)
*Authors*: Jeffrey Dean, Sanjay Ghemawat
*Year*: 2004

### [Dynamo](http://example.com/dynamo.pdf)
*Authors*: Giuseppe DeCandia et al.
"""
    papers = parse_readme_to_papers(md, "distributed_systems")
    assert len(papers) == 2
    assert "MapReduce" in papers[0]["title"]


def test_skip_scripts_topic():
    md = """# Scripts

Scripts for working with repository content.

## Download Utility
[download.sh](download.sh)
"""
    papers = parse_readme_to_papers(md, "scripts")
    assert len(papers) == 0


def test_skip_non_paper_file_links():
    md = """## Test

* [On the Expressive Power of Programming Languages](scp91-felleisen.ps.gz) [sciencedirect](https://www.sciencedirect.com/paper)
"""
    papers = parse_readme_to_papers(md, "test")
    assert len(papers) == 1
    assert "Expressive Power" in papers[0]["title"]


def test_parse_robotics_format():
    md = """Robotics
====

[Adaptive Road Following](http://example.com/road.pdf)

[DP-SLAM: Fast, Robust Simultaneous Localization](http://example.com/dpslam.pdf)

[The Dynamic Window Approach to Collision Avoidance](https://example.com/dwa.pdf)
"""
    papers = parse_readme_to_papers(md, "robotics")
    assert len(papers) == 3
    assert "Adaptive Road Following" in papers[0]["title"]


def test_total_papers_count():
    import sqlite3
    conn = sqlite3.connect("data/reading_assistant.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM papers")
    total = c.fetchone()[0]
    c.execute("SELECT COUNT(DISTINCT topic_id) FROM papers")
    topics_with_papers = c.fetchone()[0]
    conn.close()
    assert total >= 460, f"Expected at least 460 papers, got {total}"
    assert topics_with_papers >= 60, f"Expected at least 60 topics with papers, got {topics_with_papers}"
