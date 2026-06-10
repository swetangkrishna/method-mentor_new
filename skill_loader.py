"""
skill_loader.py

Reads all *_SKILL.md files from skills_M1/ (flat directory, no nesting).
Parses YAML frontmatter (name, description) and full body separately.

Two-level progressive disclosure:
  Level 1 — name + description  →  loaded into agent system prompt at startup
  Level 2 — full body           →  loaded on demand when skill is selected
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional

SKILLS_DIR = Path(__file__).parent / "skills_M1"


def _parse_skill_md(path: Path) -> Optional[Dict]:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[skill_loader] Cannot read {path}: {e}")
        return None

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", content, re.DOTALL)
    if not match:
        print(f"[skill_loader] No YAML frontmatter in {path.name}")
        return None

    fm_raw, body = match.group(1), match.group(2).strip()

    name, description_lines, in_desc = None, [], False
    for line in fm_raw.splitlines():
        if line.startswith("name:"):
            name = line.split("name:", 1)[1].strip().strip('"\'')
            in_desc = False
        elif line.startswith("description:"):
            val = line.split("description:", 1)[1].strip()
            if val.startswith(">"):
                in_desc = True
                description_lines = []
            else:
                description_lines = [val.strip('"\'')]
                in_desc = False
        elif in_desc and line.startswith("  "):
            description_lines.append(line.strip())
        elif in_desc and line.strip() and not line.startswith("  "):
            in_desc = False

    description = " ".join(description_lines).strip()

    if not name or not description:
        print(f"[skill_loader] Missing name/description in {path.name}")
        return None

    return {"name": name, "description": description, "body": body, "path": str(path)}


def load_all_skills() -> Dict[str, Dict]:
    """Load all *_SKILL.md files from skills_M1/. Returns dict keyed by skill name."""
    if not SKILLS_DIR.exists():
        raise FileNotFoundError(f"Skills directory not found: {SKILLS_DIR}")

    skills = {}
    for f in sorted(SKILLS_DIR.glob("*_SKILL.md")):
        skill = _parse_skill_md(f)
        if skill:
            skills[skill["name"]] = skill

    print(f"[skill_loader] Loaded {len(skills)} skills from {SKILLS_DIR.name}/")
    return skills


def build_skill_index(skills: Dict[str, Dict]) -> str:
    """Level-1 system prompt block: name + description only."""
    lines = [
        "## Available Pedagogical Skills\n",
        "Select the MOST APPROPRIATE skill for the current moment.\n",
        "Declare your choice BEFORE writing your response:\n",
        "  SKILL: <skill-name>\n",
        "  REASONING: <one sentence why>\n",
        "  TASK_SOLVED: YES   (only when the learner has fully achieved the goal)\n\n",
        "Skills:\n",
    ]
    for name, s in skills.items():
        lines.append(f"### {name}\n{s['description']}\n")
    return "\n".join(lines)


def get_skill_body(skills: Dict[str, Dict], skill_name: str) -> Optional[str]:
    """Level-2 retrieval: full SKILL.md body."""
    if skill_name in skills:
        return skills[skill_name]["body"]
    # fuzzy fallback
    for k in skills:
        if skill_name.lower() in k.lower() or k.lower() in skill_name.lower():
            return skills[k]["body"]
    return None


def list_skill_names(skills: Dict[str, Dict]) -> List[str]:
    return list(skills.keys())


if __name__ == "__main__":
    skills = load_all_skills()
    for name in skills:
        print(f"  {name}")
