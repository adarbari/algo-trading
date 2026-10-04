"""Keep the decision docs, ADR index, agent instructions and skills consistent."""

import re

from tests.conftest import REPO_ROOT

DOCS = REPO_ROOT / "docs"
ADR_DIR = DOCS / "adr"
SKILLS = REPO_ROOT / ".claude" / "skills"
AGENTS = REPO_ROOT / ".claude" / "agents"
# Subagents pin a model tier so routing by task risk is explicit (CLAUDE.md "Agents, models
# and tokens"); "inherit" would silently run cheap lookups on the most expensive model.
AGENT_MODELS = {"haiku", "sonnet", "opus"}
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def test_every_adr_is_indexed_and_numbered() -> None:
    index = (ADR_DIR / "README.md").read_text()
    adrs = sorted(p.name for p in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"))
    assert adrs, "no ADRs found"
    missing = [name for name in adrs if f"({name})" not in index]
    assert not missing, f"add these ADRs to docs/adr/README.md: {missing}"
    numbers = [int(name[:4]) for name in adrs]
    assert numbers == list(range(1, len(numbers) + 1)), "ADR numbers must be contiguous"


def test_every_adr_has_required_sections() -> None:
    for path in ADR_DIR.glob("[0-9][0-9][0-9][0-9]-*.md"):
        text = path.read_text()
        for section in ("**Status:**", "## Context", "## Decision", "## Consequences"):
            assert section in text, f"{path.name} is missing {section}"


def test_relative_markdown_links_resolve() -> None:
    broken = []
    for md in [*DOCS.rglob("*.md"), REPO_ROOT / "README.md", REPO_ROOT / "CLAUDE.md"]:
        for target in LINK.findall(md.read_text()):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (md.parent / target).resolve().exists():
                broken.append(f"{md.relative_to(REPO_ROOT)} -> {target}")
    assert not broken, f"broken links: {broken}"


def test_paths_named_in_agent_instructions_exist() -> None:
    text = (REPO_ROOT / "CLAUDE.md").read_text()
    referenced = set(re.findall(r"`((?:docs|\.claude/(?:skills|agents))/[^`\s]*)`", text))
    missing = [p for p in sorted(referenced) if not (REPO_ROOT / p).exists()]
    assert not missing, f"CLAUDE.md references missing paths: {missing}"


def test_skills_are_well_formed() -> None:
    skills = sorted(p for p in SKILLS.iterdir() if p.is_dir())
    assert skills
    for skill in skills:
        text = (skill / "SKILL.md").read_text()
        match = re.match(r"---\nname: (\S+)\ndescription: (.+?)\n---\n", text)
        assert match, f"{skill.name}/SKILL.md needs name + description frontmatter"
        assert match.group(1) == skill.name


def test_every_skill_is_listed_in_agent_instructions() -> None:
    text = (REPO_ROOT / "CLAUDE.md").read_text()
    unlisted = [p.name for p in SKILLS.iterdir() if f".claude/skills/{p.name}" not in text]
    assert not unlisted, f"list these skills in CLAUDE.md: {unlisted}"


def test_agents_are_well_formed_and_pin_a_model() -> None:
    agents = sorted(AGENTS.glob("*.md"))
    assert agents
    for agent in agents:
        text = agent.read_text()
        match = re.match(r"---\nname: (\S+)\ndescription: .+?\nmodel: (\S+)\n", text)
        assert match, f"{agent.name} needs name, description and model frontmatter, in that order"
        assert match.group(1) == agent.stem
        assert match.group(2) in AGENT_MODELS, f"{agent.name}: model must be one of {AGENT_MODELS}"


def test_every_agent_is_listed_in_agent_instructions() -> None:
    text = (REPO_ROOT / "CLAUDE.md").read_text()
    unlisted = [p.stem for p in AGENTS.glob("*.md") if f"`{p.stem}`" not in text]
    assert not unlisted, f"add these agents to the CLAUDE.md agents table: {unlisted}"


CLAUDE_MD_MAX_LINES = 300


def test_claude_md_stays_short_enough_to_read_every_session() -> None:
    """Detail belongs in the matching skill or doc, with a one-line pointer here."""
    lines = len((REPO_ROOT / "CLAUDE.md").read_text().splitlines())
    assert lines <= CLAUDE_MD_MAX_LINES, f"CLAUDE.md is {lines} lines (max {CLAUDE_MD_MAX_LINES})"


def test_roadmap_opens_with_a_short_now_next_section() -> None:
    text = (DOCS / "roadmap.md").read_text().splitlines()
    assert text[2].startswith("## Now / Next"), "the pickup list goes at the very top"
    end = next(i for i, line in enumerate(text[3:], 3) if line.startswith("## ") or line == "---")
    assert end - 2 <= 25, "Now / Next must stay at most 25 lines"
