import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIP_PATH = ROOT / "skills" / "ship-it" / "scripts" / "ship.py"


def load_ship():
    spec = importlib.util.spec_from_file_location("ship_it_script", SHIP_PATH)
    module = importlib.util.module_from_spec(spec)
    # Keep skills/ship-it free of __pycache__ so test runs never touch the skill folder.
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


ship = load_ship()


class ShipHelperTests(unittest.TestCase):
    def test_branch_names(self):
        self.assertEqual(ship.slugify("Add skill detail pages!"), "add-skill-detail-pages")
        self.assertEqual(ship.feature_branch_name("Add skill detail pages"), "feat/add-skill-detail-pages")
        self.assertEqual(ship.feature_branch_name("!!!"), "feat/change")
        self.assertLessEqual(len(ship.slugify("word " * 40)), 40)
        self.assertFalse(ship.slugify("word " * 40).endswith("-"))
        self.assertEqual(ship.unique_branch("feat/x", {"feat/x", "feat/x-2"}), "feat/x-3")
        self.assertEqual(ship.unique_branch("feat/y", {"feat/x"}), "feat/y")

    def test_default_and_detached_branches_are_protected(self):
        for branch in ("main", "master", "HEAD", "", "trunk"):
            with self.subTest(branch=branch):
                self.assertTrue(ship.is_protected(branch, "trunk"))
        self.assertFalse(ship.is_protected("feat/skill-detail-pages", "main"))

    def test_preview_url_prefers_the_commit_status_then_the_bot_comment(self):
        preview = "https://polite-sea-0857dd903-12.westeurope.7.azurestaticapps.net"
        statuses = [
            {"context": "ci", "state": "success", "target_url": "https://example.com/ci"},
            {"context": "hub/preview", "state": "pending", "target_url": "https://pending.azurestaticapps.net"},
            {"context": "hub/preview", "state": "success", "target_url": preview + "/"},
        ]
        self.assertEqual(ship.find_preview_url(statuses, []), preview)
        comments = [
            {"body": "Looks good"},
            {"body": f"Azure Static Web Apps: Your stage site is ready! Visit it here: {preview}"},
        ]
        self.assertEqual(ship.find_preview_url([], comments), preview)
        self.assertEqual(ship.find_preview_url(None, None), None)
        self.assertIsNone(ship.find_preview_url([], [{"body": "LGTM"}]))

    def test_hub_sha_check(self):
        sha = "a" * 40
        self.assertTrue(ship.hub_reports_sha({"build": {"sha": sha}}, sha.upper()))
        self.assertFalse(ship.hub_reports_sha({"build": {"sha": "b" * 40}}, sha))
        self.assertFalse(ship.hub_reports_sha({"build": {"sha": None}}, sha))
        self.assertFalse(ship.hub_reports_sha(None, sha))
        self.assertEqual(ship.reported_sha({"build": {"sha": "b" * 40}}), "bbbbbbb")
        self.assertEqual(ship.reported_sha(None), "an older build")

    def test_latest_run_for_commit(self):
        runs = [
            {"headSha": "b" * 40, "status": "in_progress"},
            {"headSha": "a" * 40, "status": "completed", "conclusion": "success"},
            {"headSha": "a" * 40, "status": "completed", "conclusion": "failure"},
        ]
        self.assertEqual(ship.latest_run_for(runs, "a" * 40)["conclusion"], "success")
        self.assertIsNone(ship.latest_run_for(runs, "c" * 40))
        self.assertIsNone(ship.latest_run_for(None, "a" * 40))

    def test_default_pr_body_lists_commits(self):
        body = ship.default_pr_body(["Add skill detail pages", "Polish detail page"])
        self.assertIn("- Add skill detail pages\n- Polish detail page", body)
        self.assertIn("ship-it", body)

    def test_script_never_force_pushes_or_merges(self):
        source = SHIP_PATH.read_text(encoding="utf-8")
        for forbidden in ("--force", "force-with-lease", '"merge"', "'merge'", "--admin"):
            self.assertNotIn(forbidden, source)

    def test_cli_defaults(self):
        args = ship.parse_args(["--message", "Add pages"])
        self.assertEqual(args.timeout, 300)
        self.assertEqual(args.test_command, "npm test")
        self.assertEqual(args.workflow, "deploy.yml")
        self.assertFalse(args.no_wait)


if __name__ == "__main__":
    unittest.main()
