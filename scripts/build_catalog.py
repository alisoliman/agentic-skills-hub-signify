#!/usr/bin/env python3
"""Build the agentic skills catalog.

Sources of truth:
  skills/<name>/SKILL.md          local skills: frontmatter + instructions
  catalog/local-skills.json       optional display metadata for local skills
  catalog/external-skills.json    external recommendations
  catalog/config.json             hub identity, theme and the agent skills list

Outputs:
  site/hub.json                   the single JSON file site/app.js fetches at runtime
  .github/skills/<name>/          exact copies of the skills listed in "agentSkills",
                                  so GitHub Copilot discovers them as project skills

Build metadata comes from environment variables (CI sets them):
  HUB_ENV          production | preview | local (default: local)
  HUB_BUILD_SHA    commit shown in the environment badge (the PR head SHA for previews)
  HUB_PR_NUMBER    pull request number for previews

Standard library only; runs on Python 3.9+.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
CATALOG_DIR = ROOT / "catalog"
SITE_DIR = ROOT / "site"
AGENT_SKILLS_DIR = ROOT / ".github" / "skills"

SERIES = "GitHub Innovation Series"
DEFAULT_EYEBROW = f"{SERIES} · Agentic Skills"
DEFAULT_FEATURED_SKILL = "grilling"
DEFAULT_ACCENT = "#0969da"
LIGHT_INK = "#ffffff"
DARK_INK = "#1f2328"
PAGE_BACKGROUND = "#f6f8fa"
MIN_CONTRAST = 4.5
BUILD_ENVS = ("production", "preview", "local")

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+$")
HEX_COLOR = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$")
PR_PATTERN = re.compile(r"^[0-9]+$")
IGNORED_PARTS = {".DS_Store", "Thumbs.db", "__pycache__"}
LICENSE_NAMES = {"license", "license.md", "license.txt", "copying", "notice"}


def normalize_newlines(text: str) -> str:
    """Drop a UTF-8 BOM and turn Windows line endings into \\n."""
    return text.lstrip("\ufeff").replace("\r\n", "\n")


def read_text(path: Path) -> str:
    return normalize_newlines(path.read_text(encoding="utf-8"))


def parse_scalar(raw: str) -> Any:
    value = raw.strip()
    if not value:
        return ""
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [parse_scalar(part) for part in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    return value


def split_frontmatter(markdown: str, path: Path) -> tuple[str, str]:
    """Return the (frontmatter block, body) of a SKILL.md document."""
    text = normalize_newlines(markdown)
    if not text.startswith("---\n"):
        raise ValueError(f"{path} must start with YAML frontmatter")

    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError(f"{path} is missing closing frontmatter marker")

    rest = text[end + 4:]
    newline = rest.find("\n")
    body = rest[newline + 1:] if newline != -1 else ""
    return text[4:end].strip("\n"), body


def parse_frontmatter(markdown: str, path: Path) -> dict[str, Any]:
    block, _ = split_frontmatter(markdown, path)
    metadata: dict[str, Any] = {}
    current_list_key: str | None = None

    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- ") and current_list_key:
            metadata[current_list_key].append(parse_scalar(stripped[2:]))
            continue
        current_list_key = None
        if ":" not in line:
            raise ValueError(f"Cannot parse frontmatter line in {path}: {line}")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if raw_value == "":
            metadata[key] = []
            current_list_key = key
        else:
            metadata[key] = parse_scalar(raw_value)

    return metadata


def normalize_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def local_skill_install_command(repo: str, skill_name: str) -> str:
    return f"gh skill install {repo} {skill_name}"


def external_install_command(item: Mapping[str, Any]) -> str:
    if item.get("installCommand"):
        return str(item["installCommand"])
    return f"gh skill install {item['package']} {item.get('skill') or item['name']}"


# --- Theme ---------------------------------------------------------------------


def normalize_hex(value: Any, field: str = "color") -> str:
    """Return a lowercase #rrggbb color or raise a readable ValueError."""
    text = value.strip() if isinstance(value, str) else ""
    if not HEX_COLOR.match(text):
        raise ValueError(f"{field} must be a hex color such as #0f6cbd (got {value!r})")
    text = text.lower()
    if len(text) == 4:
        text = "#" + "".join(ch * 2 for ch in text[1:])
    return text


def _rgb(color: str) -> tuple[int, int, int]:
    color = normalize_hex(color)
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(color: str) -> float:
    red, green, blue = (_linear(channel) for channel in _rgb(color))
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(first: str, second: str) -> float:
    """WCAG 2 contrast ratio between two colors, from 1.0 to 21.0."""
    lighter, darker = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def darken(color: str, amount: float) -> str:
    return "#" + "".join(f"{round(channel * (1 - amount)):02x}" for channel in _rgb(color))


def readable_on(background: str, color: str) -> str:
    """Darken `color` just enough to reach MIN_CONTRAST against `background`."""
    for step in range(21):
        candidate = darken(color, step * 0.05)
        if contrast_ratio(candidate, background) >= MIN_CONTRAST:
            return candidate
    return DARK_INK


def resolve_theme(theme: Any) -> dict[str, Any]:
    """Resolve config "theme" into the colors the site applies as CSS custom properties.

    accent  brand color for buttons, active filters and focus rings
    ink     text on top of the accent; defaults to white or near-black, whichever reads better
    link    the accent, darkened if needed so links stay readable on the page background
    """
    if theme is None:
        theme = {}
    if not isinstance(theme, Mapping):
        raise ValueError('theme must be an object such as {"accent": "#0f6cbd"}')
    accent = normalize_hex(theme.get("accent") or DEFAULT_ACCENT, "theme.accent")
    if theme.get("ink"):
        ink = normalize_hex(theme["ink"], "theme.ink")
    else:
        ink = max((LIGHT_INK, DARK_INK), key=lambda candidate: contrast_ratio(accent, candidate))
    return {
        "accent": accent,
        "ink": ink,
        "link": readable_on(PAGE_BACKGROUND, accent),
        "inkContrast": round(contrast_ratio(accent, ink), 2),
    }


# --- Config --------------------------------------------------------------------


def agent_skill_names(config: Mapping[str, Any]) -> list[str]:
    names = config.get("agentSkills", [])
    if not isinstance(names, list) or not all(
        isinstance(name, str) and NAME_PATTERN.match(name) for name in names
    ):
        raise ValueError("config 'agentSkills' must be a list of skill folder names")
    if len(set(names)) != len(names):
        raise ValueError("config 'agentSkills' lists a skill more than once")
    return list(names)


def default_notice(customer: str) -> str:
    subject = f"an official {customer} system" if customer else "an official or production system"
    return f"Demo content for a {SERIES} session. This hub is not {subject}."


def load_config() -> dict[str, Any]:
    path = CATALOG_DIR / "config.json"
    config = json.loads(read_text(path))
    if not isinstance(config, dict):
        raise ValueError(f"{path} must contain a JSON object")
    for key in ("title", "tagline", "owner", "repo"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"{path}: '{key}' is required")
    if not REPO_PATTERN.match(config["repo"]):
        raise ValueError(f"{path}: 'repo' must look like owner/name (got {config['repo']!r})")
    agent_skill_names(config)
    resolve_theme(config.get("theme"))
    return config


def public_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """The config as the site sees it: defaults applied and the theme resolved."""
    customer = str(config.get("customer") or "").strip()
    return {
        "customer": customer,
        "eyebrow": config.get("eyebrow") or DEFAULT_EYEBROW,
        "title": config["title"],
        "tagline": config["tagline"],
        "owner": config["owner"],
        "repo": config["repo"],
        "hubUrl": config.get("hubUrl") or "",
        "primaryCta": config.get("primaryCta") or "",
        "featuredSkill": config.get("featuredSkill") or DEFAULT_FEATURED_SKILL,
        "notice": config.get("notice") or default_notice(customer),
        "theme": resolve_theme(config.get("theme")),
        "agentSkills": agent_skill_names(config),
    }


# --- Skill files and context footprint -------------------------------------------


def skill_files(root: Path) -> list[Path]:
    """All files in a skill folder, ignoring OS metadata and Python caches."""
    if not root.is_dir():
        return []
    files = []
    for path in root.rglob("*"):
        parts = path.relative_to(root).parts
        if path.is_file() and not any(part in IGNORED_PARTS or part.endswith(".pyc") for part in parts):
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def supporting_files(skill_dir: Path) -> list[Path]:
    """Files an agent may read on demand: everything except SKILL.md, licenses and dotfiles."""
    result = []
    for path in skill_files(skill_dir):
        rel = path.relative_to(skill_dir)
        if rel.as_posix() == "SKILL.md" or rel.name.startswith("."):
            continue
        if len(rel.parts) == 1 and rel.name.lower() in LICENSE_NAMES:
            continue
        result.append(path)
    return result


def estimate_tokens(chars: int) -> int:
    """Rough token estimate: about four characters per token."""
    return math.ceil(chars / 4)


def text_length(path: Path) -> int:
    try:
        return len(read_text(path))
    except (UnicodeDecodeError, OSError):
        return 0


def context_footprint(skill_dir: Path, metadata: Mapping[str, Any], body: str) -> dict[str, int]:
    """Estimate what a skill costs in the agent's context, by when it is loaded.

    indexTokens  name + description: always loaded, so the agent knows the skill exists
    bodyTokens   SKILL.md instructions: loaded when the agent decides to use the skill
    files        supporting files (references, scripts): read only if the instructions need them
    """
    name = str(metadata.get("name") or skill_dir.name)
    description = str(metadata.get("description") or "")
    files = supporting_files(skill_dir)
    return {
        "indexTokens": estimate_tokens(len(name) + len(description)),
        "bodyTokens": estimate_tokens(len(body.strip())),
        "files": len(files),
        "fileTokens": estimate_tokens(sum(text_length(path) for path in files)),
    }


# --- Agent skills (.github/skills) -----------------------------------------------


def _file_map(root: Path) -> dict[str, Path]:
    return {path.relative_to(root).as_posix(): path for path in skill_files(root)}


def agent_skill_drift(
    config: Mapping[str, Any],
    skills_dir: Optional[Path] = None,
    target_dir: Optional[Path] = None,
) -> list[str]:
    """Differences between skills/<name> and its committed copy in .github/skills/<name>."""
    skills_dir = skills_dir or SKILLS_DIR
    target_dir = target_dir or AGENT_SKILLS_DIR
    problems = []
    for name in agent_skill_names(config):
        source = _file_map(skills_dir / name)
        if "SKILL.md" not in source:
            problems.append(f"skills/{name}/SKILL.md does not exist")
            continue
        copy = _file_map(target_dir / name)
        for rel in sorted(set(source) | set(copy)):
            label = f".github/skills/{name}/{rel}"
            if rel not in copy:
                problems.append(f"{label} is missing")
            elif rel not in source:
                problems.append(f"{label} is stale (not in skills/{name})")
            elif source[rel].read_bytes() != copy[rel].read_bytes():
                problems.append(f"{label} differs from skills/{name}/{rel}")
    return problems


def sync_agent_skills(
    config: Mapping[str, Any],
    skills_dir: Optional[Path] = None,
    target_dir: Optional[Path] = None,
) -> list[str]:
    """Copy each agent skill into .github/skills/<name>, removing stale files only there."""
    skills_dir = skills_dir or SKILLS_DIR
    target_dir = target_dir or AGENT_SKILLS_DIR
    changes = []
    for name in agent_skill_names(config):
        source = _file_map(skills_dir / name)
        if "SKILL.md" not in source:
            raise ValueError(f"agentSkills lists '{name}' but skills/{name}/SKILL.md does not exist")
        copy_root = target_dir / name
        copy = _file_map(copy_root)
        for rel, path in source.items():
            data = path.read_bytes()
            if rel in copy and copy[rel].read_bytes() == data:
                continue
            target = copy_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            shutil.copymode(path, target)
            changes.append(f"updated .github/skills/{name}/{rel}")
        for rel in sorted(set(copy) - set(source)):
            copy[rel].unlink()
            changes.append(f"removed .github/skills/{name}/{rel}")
        _remove_empty_dirs(copy_root)
    return changes


def _remove_empty_dirs(root: Path) -> None:
    directories = sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in directories:
        if not any(directory.iterdir()):
            directory.rmdir()


# --- Catalog entries ---------------------------------------------------------------


def load_display_metadata() -> dict[str, Any]:
    path = CATALOG_DIR / "local-skills.json"
    if not path.is_file():
        return {}
    data = json.loads(read_text(path))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must be a JSON object keyed by skill name")
    return data


def validate_skill_name(name: Any) -> None:
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name):
        raise ValueError(f"Skill name must be a lowercase URL-safe slug (got {name!r})")


def validate_source_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or any(char.isspace() or ord(char) < 32 for char in value)
    ):
        raise ValueError(f"Source link must be an HTTPS URL (got {value!r})")
    return value


def skill_details(raw: Any, canonical_source: str = "") -> dict[str, str]:
    fields = (
        "whatItDoes", "whenToUse", "whenNotToUse", "exampleTask",
        "author", "publisher", "canonicalSource", "guidanceOrigin",
    )
    if not isinstance(raw, dict) or set(raw) - set(fields):
        raise ValueError("Skill details must be an object with recognized guidance and attribution fields")
    details = {}
    for field in fields:
        value = raw.get(field, "")
        if not isinstance(value, str) or any(ord(char) < 32 for char in value):
            raise ValueError(f"Skill details.{field} must be plain text")
        details[field] = value.strip()
    if details["canonicalSource"]:
        validate_source_url(details["canonicalSource"])
    if canonical_source:
        if details["canonicalSource"] and details["canonicalSource"] != canonical_source:
            raise ValueError("Local canonical source must link to the checked-in SKILL.md")
        details["canonicalSource"] = validate_source_url(canonical_source)
    if details["guidanceOrigin"] not in ("", "demo"):
        raise ValueError("Skill details.guidanceOrigin must be 'demo' or empty")
    if any(details[field] for field in fields[:4]) and details["guidanceOrigin"] != "demo":
        raise ValueError("Curated skill guidance must be labeled with guidanceOrigin 'demo'")
    return details


def load_local_skills(config: Mapping[str, Any]) -> list[dict[str, Any]]:
    display_path = CATALOG_DIR / "local-skills.json"
    display_metadata = load_display_metadata()
    agent_skills = set(agent_skill_names(config))
    skills: list[dict[str, Any]] = []
    for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        text = read_text(skill_file)
        metadata = parse_frontmatter(text, skill_file)
        _, body = split_frontmatter(text, skill_file)
        folder = skill_file.parent.name
        name = str(metadata.get("name") or folder)
        if not metadata.get("description"):
            raise ValueError(f"{skill_file} needs a description")
        if name != folder:
            raise ValueError(f"{skill_file}: name '{name}' must match its folder name '{folder}'")
        validate_skill_name(name)
        display = display_metadata.get(name, {})
        skills.append(
            {
                "name": name,
                "title": display.get("title") or metadata.get("title") or name.replace("-", " ").title(),
                "description": display.get("description") or str(metadata["description"]),
                "license": display.get("license") or metadata.get("license") or "Unspecified",
                "source": display.get("source") or metadata.get("source") or "local",
                "kind": "local",
                "agentSkill": name in agent_skills,
                "tags": normalize_tags(display.get("tags", metadata.get("tags"))),
                "url": f"https://github.com/{config['repo']}/tree/main/skills/{folder}",
                "installCommand": local_skill_install_command(config["repo"], name),
                "footprint": context_footprint(skill_file.parent, metadata, body),
                "details": skill_details(
                    display.get("details", {}),
                    f"https://github.com/{config['repo']}/blob/main/skills/{folder}/SKILL.md",
                ),
            }
        )
    known = {skill["name"] for skill in skills}
    unknown = set(display_metadata) - known
    if unknown:
        raise ValueError(f"{display_path}: metadata for unknown skills: {', '.join(sorted(unknown))}")
    missing = agent_skills - known
    if missing:
        raise ValueError(f"config 'agentSkills' lists skills that are not in skills/: {', '.join(sorted(missing))}")
    return skills


def load_external_skills() -> list[dict[str, Any]]:
    source_path = CATALOG_DIR / "external-skills.json"
    items = json.loads(read_text(source_path))
    skills: list[dict[str, Any]] = []
    for item in items:
        for required in ("name", "title", "description", "package", "url"):
            if not item.get(required):
                raise ValueError(f"{source_path}: external entry missing {required}")
        validate_skill_name(item["name"])
        validate_source_url(item["url"])
        skills.append(
            {
                "name": item["name"],
                "title": item["title"],
                "description": item["description"],
                "license": item.get("license", "See source"),
                "source": item.get("source") or item["package"],
                "kind": "external",
                "agentSkill": False,
                "tags": normalize_tags(item.get("tags")),
                "url": item["url"],
                "installCommand": external_install_command(item),
                "package": item["package"],
                "details": skill_details(item.get("details", {})),
            }
        )
    return skills


# --- Build -----------------------------------------------------------------------


def build_metadata(environ: Optional[Mapping[str, str]] = None) -> dict[str, Any]:
    """Data for the environment badge: production, preview (pull request) or local."""
    environ = os.environ if environ is None else environ
    env = (environ.get("HUB_ENV") or "local").strip().lower()
    if env not in BUILD_ENVS:
        raise ValueError(f"HUB_ENV must be one of {', '.join(BUILD_ENVS)} (got {env!r})")
    sha = (environ.get("HUB_BUILD_SHA") or "").strip().lower() or None
    if sha is not None and not SHA_PATTERN.match(sha):
        raise ValueError(f"HUB_BUILD_SHA must be a hex commit SHA (got {sha!r})")
    pr_text = (environ.get("HUB_PR_NUMBER") or "").strip()
    if pr_text and not PR_PATTERN.match(pr_text):
        raise ValueError(f"HUB_PR_NUMBER must be a number (got {pr_text!r})")
    pr = int(pr_text) if pr_text else None
    short_sha = sha[:7] if sha else None
    if env == "production":
        parts = ["Production", short_sha]
    elif env == "preview":
        parts = ["Preview", f"PR #{pr}" if pr else None, short_sha]
    else:
        parts = ["Local build"]
    return {
        "env": env,
        "sha": sha,
        "shortSha": short_sha,
        "pr": pr,
        "label": " · ".join(part for part in parts if part),
    }


def build_hub(config: Mapping[str, Any], environ: Optional[Mapping[str, str]] = None) -> dict[str, Any]:
    skills = sorted(
        load_local_skills(config) + load_external_skills(),
        key=lambda item: (0 if item["kind"] == "local" else 1, item["title"].lower()),
    )
    names = [skill["name"] for skill in skills]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"Skill names must be unique across the catalog: {', '.join(duplicates)}")
    return {
        "schemaVersion": 2,
        "build": build_metadata(environ),
        "config": public_config(config),
        "skills": skills,
    }


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def build(environ: Optional[Mapping[str, str]] = None) -> Path:
    config = load_config()
    changes = sync_agent_skills(config)
    hub = build_hub(config, environ)
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SITE_DIR / "hub.json"
    with open(out_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(hub, indent=2) + "\n")
    for change in changes:
        print(change)
    print(
        f"Built {len(hub['skills'])} skills into {_display_path(out_path)} "
        f"[{hub['build']['label']}]; agent skills in .github/skills: "
        f"{', '.join(agent_skill_names(config)) or 'none'}"
    )
    return out_path


def main() -> int:
    try:
        build()
    except ValueError as error:
        print(f"Build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
