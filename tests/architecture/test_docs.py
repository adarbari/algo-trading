"""Keep the decision docs, ADR index, agent instructions and skills consistent."""

import re

from tests.conftest import REPO_ROOT

DOCS = REPO_ROOT / "docs"
ADR_DIR = DOCS / "adr"
SKILLS = REPO_ROOT / ".claude" / "skills"
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
    referenced = set(re.findall(r"`((?:docs|\.claude/skills)/[^`\s]+)`", text))
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
