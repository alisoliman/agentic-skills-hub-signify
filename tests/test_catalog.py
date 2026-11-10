import io
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlparse

from scripts import build_catalog as catalog

SHA = "0123456789abcdef0123456789abcdef01234567"


class StaticLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.ids = set()
        self.anchor_targets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.anchor_targets.append(attrs.get("target", "_self"))
        if "id" in attrs:
            self.ids.add(attrs["id"])
        for attr in ("href", "src"):
            if attr in attrs:
                self.links.append(attrs[attr])


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class FrontmatterTests(unittest.TestCase):
    def test_frontmatter_and_tags(self):
        metadata = catalog.parse_frontmatter(
            "---\nname: sample\ndescription: 'A sample skill'\ntags:\n"
            "  - demo\n  - planning\n---\nInstructions",
            Path("sample/SKILL.md"),
        )
        self.assertEqual(metadata["description"], "A sample skill")
        self.assertEqual(catalog.normalize_tags(metadata["tags"]), ["demo", "planning"])
        self.assertEqual(catalog.parse_scalar("[demo, design]"), ["demo", "design"])

    def test_malformed_frontmatter_fails_explicitly(self):
        for text in ("name: sample", "---\nname: sample", "---\ninvalid\n---\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                catalog.parse_frontmatter(text, Path("sample/SKILL.md"))

    def test_windows_line_endings_and_bom_are_accepted(self):
        text = "\ufeff---\r\nname: sample\r\ndescription: A sample\r\n---\r\nBody line\r\n"
        self.assertEqual(catalog.parse_frontmatter(text, Path("x"))["description"], "A sample")
        self.assertEqual(catalog.split_frontmatter(text, Path("x"))[1], "Body line\n")


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.config = catalog.load_config()

    def test_local_metadata_and_source_paths(self):
        skills = catalog.load_local_skills(self.config)
        by_name = {skill["name"]: skill for skill in skills}
        for name in ("grilling", "frontend-design", "ship-it", "microsoft-foundry"):
            self.assertIn(name, by_name)
        self.assertNotIn("grill-me", by_name)
        self.assertEqual(by_name["grilling"]["license"], "MIT")
        self.assertEqual(by_name["frontend-design"]["license"], "Apache-2.0")
        self.assertEqual(by_name["ship-it"]["license"], "MIT")
        prefix = f"https://github.com/{self.config['repo']}/tree/main/"
        for skill in skills:
            with self.subTest(skill=skill["name"]):
                self.assertEqual(skill["kind"], "local")
                self.assertTrue(skill["description"])
                self.assertTrue(skill["url"].startswith(prefix))
                source = catalog.ROOT / skill["url"][len(prefix):]
                metadata = catalog.parse_frontmatter(
                    (source / "SKILL.md").read_text(encoding="utf-8"), source / "SKILL.md"
                )
                self.assertEqual(metadata["name"], skill["name"])
                self.assertEqual(
                    skill["installCommand"], f"gh skill install {self.config['repo']} {skill['name']}"
                )

    def test_agent_skills_are_flagged_and_foundry_stays_catalog_only(self):
        skills = {skill["name"]: skill for skill in catalog.load_local_skills(self.config)}
        for name in ("grilling", "frontend-design", "ship-it"):
            self.assertIn(name, self.config["agentSkills"])
            self.assertTrue(skills[name]["agentSkill"])
        self.assertNotIn("microsoft-foundry", self.config["agentSkills"])
        self.assertFalse(skills["microsoft-foundry"]["agentSkill"])

    def test_agent_skill_copies_match_canonical_skills(self):
        problems = catalog.agent_skill_drift(self.config)
        self.assertEqual(
            problems, [], "Run `npm run build` to refresh .github/skills: " + "; ".join(problems)
        )

    def test_selected_project_skills_include_supporting_files(self):
        for name, files in {
            "grilling": ["SKILL.md", "agents/openai.yaml", "LICENSE"],
            "frontend-design": ["SKILL.md", "LICENSE.txt"],
            "ship-it": ["SKILL.md", "LICENSE", "scripts/ship.py"],
        }.items():
            for file in files:
                with self.subTest(skill=name, file=file):
                    self.assertTrue((catalog.AGENT_SKILLS_DIR / name / file).is_file())

    def test_unknown_display_metadata_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "local-skills.json", '{"does-not-exist": {}}')
            with patch.object(catalog, "CATALOG_DIR", root):
                with self.assertRaisesRegex(ValueError, "metadata for unknown skills"):
                    catalog.load_local_skills(self.config)

    def test_missing_skill_description_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "sample" / "SKILL.md", "---\nname: sample\n---\n")
            with patch.object(catalog, "SKILLS_DIR", root):
                with self.assertRaisesRegex(ValueError, "needs a description"):
                    catalog.load_local_skills(self.config)

    def test_skill_name_must_match_its_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "sample" / "SKILL.md", "---\nname: other\ndescription: x\n---\n")
            with patch.object(catalog, "SKILLS_DIR", root), patch.object(catalog, "CATALOG_DIR", root):
                with self.assertRaisesRegex(ValueError, "must match its folder"):
                    catalog.load_local_skills(self.config)

    def test_unknown_agent_skill_fails_explicitly(self):
        config = dict(self.config, agentSkills=["does-not-exist"])
        with self.assertRaisesRegex(ValueError, "not in skills/"):
            catalog.load_local_skills(config)

    def test_external_entries_and_required_fields(self):
        for skill in catalog.load_external_skills():
            self.assertEqual(skill["kind"], "external")
            self.assertEqual(urlparse(skill["url"]).scheme, "https")
            self.assertTrue(skill["installCommand"].startswith("gh skill install "))
            self.assertNotIn("installs", skill)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "external-skills.json", '[{"name": "incomplete"}]')
            with patch.object(catalog, "CATALOG_DIR", root):
                with self.assertRaisesRegex(ValueError, "external entry missing title"):
                    catalog.load_external_skills()

    def test_external_install_command_uses_package_and_skill(self):
        item = {"name": "git-commit", "package": "github/awesome-copilot", "skill": "git-commit"}
        self.assertEqual(
            catalog.external_install_command(item), "gh skill install github/awesome-copilot git-commit"
        )

    def test_context_footprint_separates_index_body_and_files(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "sample"
            text = "---\nname: sample\ndescription: abcd\n---\n" + "x" * 40 + "\n"
            write(skill / "SKILL.md", text)
            write(skill / "LICENSE", "not counted")
            write(skill / ".gitignore", "")
            write(skill / "__pycache__" / "cache.pyc", "not counted")
            write(skill / "references" / "guide.md", "y" * 81)
            metadata = catalog.parse_frontmatter(text, skill / "SKILL.md")
            _, body = catalog.split_frontmatter(text, skill / "SKILL.md")
            footprint = catalog.context_footprint(skill, metadata, body)
        self.assertEqual(footprint, {"indexTokens": 3, "bodyTokens": 10, "files": 1, "fileTokens": 21})

    def test_foundry_footprint_shows_progressive_disclosure(self):
        skills = {skill["name"]: skill for skill in catalog.load_local_skills(self.config)}
        foundry = skills["microsoft-foundry"]["footprint"]
        self.assertGreater(foundry["files"], 50)
        self.assertGreater(foundry["fileTokens"], 20 * foundry["indexTokens"])

    def test_details_expose_guidance_and_local_canonical_instruction_sources(self):
        for skill in catalog.load_local_skills(self.config) + catalog.load_external_skills():
            details = skill["details"]
            for field in ("whatItDoes", "whenToUse", "whenNotToUse", "exampleTask"):
                self.assertTrue(details[field], f"{skill['name']}: {field}")
            self.assertEqual(details["guidanceOrigin"], "demo")
            self.assertTrue(details["author"] or details["publisher"])
            self.assertEqual(urlparse(details["canonicalSource"]).scheme, "https")
            if skill["kind"] == "local":
                expected = f"https://github.com/{self.config['repo']}/blob/main/skills/{skill['name']}/SKILL.md"
                self.assertEqual(details["canonicalSource"], expected)

    def test_missing_details_remain_empty_and_invalid_details_fail_explicitly(self):
        self.assertTrue(all(value == "" for value in catalog.skill_details({}).values()))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "external-skills.json", json.dumps([{
                "name": "incomplete-guidance", "title": "Incomplete guidance", "description": "Demo",
                "package": "o/r", "url": "https://example.com/catalog",
            }]))
            with patch.object(catalog, "CATALOG_DIR", root):
                skill = catalog.load_external_skills()[0]
            self.assertTrue(all(value == "" for value in skill["details"].values()))
            self.assertEqual(skill["url"], "https://example.com/catalog")
        for details in (
            None, [], {"whenToUse": 42}, {"author": ["Unknown"]}, {"whatItDoes": "x\n"},
            {"unexpected": "typo"}, {"guidanceOrigin": "official"},
            {"whenToUse": "Unlabeled guidance"},
            {"canonicalSource": "http://example.com/SKILL.md"},
            {"canonicalSource": "https:///SKILL.md"},
            {"canonicalSource": "https://example.com/a b"},
            {"canonicalSource": "https://user:password@example.com"},
        ):
            with self.subTest(details=details), self.assertRaises(ValueError):
                catalog.skill_details(details)
        with self.assertRaisesRegex(ValueError, "checked-in SKILL.md"):
            catalog.skill_details({"canonicalSource": "https://example.com"}, "https://github.com/o/r/blob/main/skills/a/SKILL.md")

    def test_stable_ids_reject_invalid_names_and_cross_kind_duplicates(self):
        for name in ("Uppercase", "with space", "../skill", "under_score", "a--b", "", 42):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "URL-safe slug"):
                catalog.validate_skill_name(name)
        local = {"name": "same-id", "title": "First title", "kind": "local"}
        external = {"name": "same-id", "title": "Renamed title", "kind": "external"}
        with patch.object(catalog, "load_local_skills", return_value=[local]), patch.object(
            catalog, "load_external_skills", return_value=[external]
        ):
            with self.assertRaisesRegex(ValueError, "unique across the catalog"):
                catalog.build_hub(self.config)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "Bad-ID" / "SKILL.md", "---\nname: Bad-ID\ndescription: x\n---\n")
            with patch.object(catalog, "SKILLS_DIR", root), patch.object(catalog, "CATALOG_DIR", root):
                with self.assertRaisesRegex(ValueError, "URL-safe slug"):
                    catalog.load_local_skills(self.config)
            write(root / "external-skills.json", json.dumps([dict(
                external, name="bad/id", description="x", package="o/r", url="https://example.com"
            )]))
            with patch.object(catalog, "CATALOG_DIR", root):
                with self.assertRaisesRegex(ValueError, "URL-safe slug"):
                    catalog.load_external_skills()


class AgentSkillSyncTests(unittest.TestCase):
    def test_sync_copies_and_removes_stale_files_only_inside_agent_skills(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_dir, target = root / "skills", root / ".github" / "skills"
            write(skills_dir / "alpha" / "SKILL.md", "---\nname: alpha\ndescription: A\n---\nBody\n")
            write(skills_dir / "alpha" / "scripts" / "run.py", "print('hi')\n")
            write(target / "alpha" / "old" / "stale.md", "stale\n")
            write(target / "other" / "SKILL.md", "not an agent skill, left alone\n")
            config = {"agentSkills": ["alpha"]}

            self.assertTrue(catalog.agent_skill_drift(config, skills_dir, target))
            changes = catalog.sync_agent_skills(config, skills_dir, target)

            self.assertIn("removed .github/skills/alpha/old/stale.md", changes)
            self.assertEqual(
                (target / "alpha" / "scripts" / "run.py").read_bytes(),
                (skills_dir / "alpha" / "scripts" / "run.py").read_bytes(),
            )
            self.assertFalse((target / "alpha" / "old").exists())
            self.assertTrue((target / "other" / "SKILL.md").exists())
            self.assertEqual(catalog.agent_skill_drift(config, skills_dir, target), [])
            self.assertEqual(catalog.sync_agent_skills(config, skills_dir, target), [])

    def test_caches_and_os_files_never_count_as_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_dir, target = root / "skills", root / ".github" / "skills"
            write(skills_dir / "alpha" / "SKILL.md", "---\nname: alpha\ndescription: A\n---\n")
            config = {"agentSkills": ["alpha"]}
            catalog.sync_agent_skills(config, skills_dir, target)
            write(skills_dir / "alpha" / "scripts" / "__pycache__" / "ship.cpython-312.pyc", "cache")
            write(skills_dir / "alpha" / ".DS_Store", "finder")
            write(target / "alpha" / ".DS_Store", "finder")
            self.assertEqual(catalog.agent_skill_drift(config, skills_dir, target), [])
            self.assertEqual(catalog.sync_agent_skills(config, skills_dir, target), [])
            self.assertFalse((target / "alpha" / "scripts").exists())

    def test_missing_agent_skill_source_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "does not exist"):
                catalog.sync_agent_skills({"agentSkills": ["ghost"]}, root / "skills", root / "target")


class ThemeTests(unittest.TestCase):
    def test_contrast_ratio_matches_wcag_reference_values(self):
        self.assertAlmostEqual(catalog.contrast_ratio("#000000", "#ffffff"), 21.0, places=2)
        self.assertAlmostEqual(catalog.contrast_ratio("#777777", "#ffffff"), 4.48, places=2)

    def test_theme_defaults_and_readable_links(self):
        theme = catalog.resolve_theme({"accent": "#0F6CBD"})
        self.assertEqual(theme["accent"], "#0f6cbd")
        self.assertEqual(theme["ink"], "#ffffff")
        self.assertGreaterEqual(theme["inkContrast"], 4.5)
        light = catalog.resolve_theme({"accent": "#ff6200"})
        self.assertEqual(light["ink"], catalog.DARK_INK)
        self.assertGreaterEqual(catalog.contrast_ratio(light["link"], catalog.PAGE_BACKGROUND), 4.5)
        self.assertEqual(catalog.resolve_theme({"accent": "#abc"})["accent"], "#aabbcc")
        self.assertEqual(catalog.resolve_theme(None)["accent"], catalog.DEFAULT_ACCENT)

    def test_invalid_colors_fail_explicitly(self):
        for theme in ({"accent": "blue"}, {"accent": "#12345"}, {"accent": "#0f6cbd", "ink": "white"}, "red"):
            with self.subTest(theme=theme), self.assertRaises(ValueError):
                catalog.resolve_theme(theme)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.config = catalog.load_config()

    def test_build_metadata_labels(self):
        self.assertEqual(catalog.build_metadata({})["label"], "Local build")
        production = catalog.build_metadata({"HUB_ENV": "production", "HUB_BUILD_SHA": SHA})
        self.assertEqual(production["label"], "Production · 0123456")
        self.assertEqual(production["sha"], SHA)
        preview = catalog.build_metadata(
            {"HUB_ENV": "preview", "HUB_BUILD_SHA": SHA.upper(), "HUB_PR_NUMBER": "12"}
        )
        self.assertEqual(preview["label"], "Preview · PR #12 · 0123456")
        self.assertEqual(preview["pr"], 12)
        self.assertEqual(preview["sha"], SHA)

    def test_invalid_build_metadata_fails_explicitly(self):
        for environ in ({"HUB_ENV": "staging"}, {"HUB_BUILD_SHA": "not-a-sha"}, {"HUB_PR_NUMBER": "12a"}):
            with self.subTest(environ=environ), self.assertRaises(ValueError):
                catalog.build_metadata(environ)

    def test_customer_copy_and_honest_notice(self):
        branded = catalog.public_config(dict(self.config, customer="Contoso"))
        self.assertIn("not an official Contoso system", branded["notice"])
        template = catalog.public_config(dict(self.config, customer=""))
        self.assertIn("not an official or production system", template["notice"])
        self.assertEqual(template["featuredSkill"], "grilling")

    def test_build_writes_a_valid_deterministic_hub(self):
        environ = {"HUB_ENV": "preview", "HUB_BUILD_SHA": "abcdef1234567", "HUB_PR_NUMBER": "7"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(catalog, "ROOT", root), patch.object(catalog, "SITE_DIR", root / "site"), patch.object(
                catalog, "AGENT_SKILLS_DIR", root / ".github" / "skills"
            ), patch("sys.stdout", new_callable=io.StringIO):
                first = catalog.build(environ).read_bytes()
                second = catalog.build(environ).read_bytes()
            self.assertTrue((root / ".github" / "skills" / "grilling" / "SKILL.md").is_file())
        self.assertEqual(first, second)
        hub = json.loads(first)
        self.assertEqual(hub["schemaVersion"], 2)
        self.assertEqual(hub["build"]["label"], "Preview · PR #7 · abcdef1")
        self.assertEqual(hub["config"]["repo"], self.config["repo"])
        self.assertTrue(hub["config"]["notice"].startswith("Demo content"))
        names = [skill["name"] for skill in hub["skills"]]
        self.assertEqual(len(names), len(set(names)))
        for skill in hub["skills"]:
            with self.subTest(skill=skill["name"]):
                for key in ("name", "title", "description", "source", "license", "url", "installCommand"):
                    self.assertIsInstance(skill[key], str)
                    self.assertTrue(skill[key])
                self.assertTrue(skill["installCommand"].startswith("gh skill install "))
                self.assertTrue(all(isinstance(tag, str) and tag for tag in skill["tags"]))
                if skill["kind"] == "local":
                    self.assertEqual(set(skill["footprint"]), {"indexTokens", "bodyTokens", "files", "fileTokens"})


class SiteTests(unittest.TestCase):
    def test_static_index_links_resolve_and_stay_in_the_same_tab(self):
        page = StaticLinks()
        page.feed((catalog.SITE_DIR / "index.html").read_text(encoding="utf-8"))
        self.assertTrue(all(target == "_self" for target in page.anchor_targets))
        for link in page.links:
            parsed = urlparse(link)
            if parsed.scheme:
                self.assertEqual(parsed.scheme, "https")
            elif parsed.path:
                self.assertTrue(parsed.path.startswith("/"), f"use a root-absolute path: {link}")
                target = unquote(parsed.path).lstrip("/") or "index.html"
                self.assertTrue((catalog.SITE_DIR / target).is_file(), link)
            elif parsed.fragment:
                self.assertIn(parsed.fragment, page.ids)
        for element_id in (
            "build-badge", "hub-notice", "hub-eyebrow", "skills-grid",
            "skill-detail", "return-to-catalog", "copy-status",
        ):
            self.assertIn(element_id, page.ids)

    def test_navigation_fallback_serves_routes_but_not_data_or_assets(self):
        config = json.loads((catalog.SITE_DIR / "staticwebapp.config.json").read_text(encoding="utf-8"))
        fallback = config["navigationFallback"]
        self.assertEqual(fallback["rewrite"], "/index.html")
        self.assertIn("/hub.json", fallback["exclude"])
        self.assertTrue(any("css" in pattern and "js" in pattern for pattern in fallback["exclude"]))
        self.assertEqual(config["globalHeaders"]["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
