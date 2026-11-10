#!/usr/bin/env python3
"""Ship the current change for review.

Runs the tests, moves the work onto a feature branch, commits it, pushes, opens or
updates the pull request, then waits for the Azure Static Web Apps preview of that
pull request and checks that <preview>/hub.json reports the pushed commit.

It never merges, never pushes to the default branch and never force-pushes.

Run it from anywhere inside the repository:
  python3 .github/skills/ship-it/scripts/ship.py --message "Add skill detail pages"
  (Windows: py -3 .github/skills/ship-it/scripts/ship.py --message "...")

The last lines are machine-readable:
  PR_URL=https://github.com/<owner>/<repo>/pull/<number>
  PREVIEW_URL=https://<app>-<number>.<region>.<n>.azurestaticapps.net

Exit codes: 0 shipped, 1 tests failed, 2 refused or git/GitHub error,
3 preview not verified (timeout or failed deploy). Re-running is safe: it does not
create duplicate commits or pull requests.

Standard library only (Python 3.9+). Needs git, gh (signed in) and npm on PATH.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Optional

PROTECTED_BRANCHES = {"main", "master"}
PREVIEW_STATUS_CONTEXT = "hub/preview"
PREVIEW_URL_PATTERN = re.compile(r"https://[A-Za-z0-9.-]+\.azurestaticapps\.net[^\s)\]>\"'<]*")
FAILED_CONCLUSIONS = {"failure", "cancelled", "timed_out", "startup_failure"}
NO_PREVIEW_GRACE_SECONDS = 60


class ShipError(Exception):
    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


def log(message: str) -> None:
    print(f"[ship-it] {message}", flush=True)


# --- Pure helpers (unit tested) ----------------------------------------------------


def slugify(text: str, max_length: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if len(slug) > max_length:
        cut = slug[:max_length]
        slug = cut.rsplit("-", 1)[0] if "-" in cut else cut
    return slug.strip("-") or "change"


def feature_branch_name(text: str) -> str:
    return f"feat/{slugify(text)}"


def unique_branch(base: str, existing: Iterable[str]) -> str:
    taken = set(existing)
    if base not in taken:
        return base
    counter = 2
    while f"{base}-{counter}" in taken:
        counter += 1
    return f"{base}-{counter}"


def is_protected(branch: str, default_branch: str) -> bool:
    return branch in PROTECTED_BRANCHES or branch == default_branch or branch in ("", "HEAD")


def clean_url(url: str) -> str:
    return url.strip().rstrip("/.,;:")


def find_preview_url(statuses: Any, comments: Any) -> Optional[str]:
    """Preview URL from the deploy workflow's commit status, else from the bot's PR comment."""
    for status in statuses if isinstance(statuses, list) else []:
        if (
            status.get("context") == PREVIEW_STATUS_CONTEXT
            and status.get("state") == "success"
            and status.get("target_url")
        ):
            return clean_url(status["target_url"])
    for comment in reversed(comments if isinstance(comments, list) else []):
        match = PREVIEW_URL_PATTERN.search(comment.get("body") or "")
        if match:
            return clean_url(match.group(0))
    return None


def hub_reports_sha(payload: Any, sha: str) -> bool:
    build = payload.get("build") if isinstance(payload, dict) else None
    return isinstance(build, dict) and str(build.get("sha") or "").lower() == sha.lower()


def reported_sha(payload: Any) -> str:
    build = payload.get("build") if isinstance(payload, dict) else None
    sha = build.get("sha") if isinstance(build, dict) else None
    return str(sha)[:7] if sha else "an older build"


def latest_run_for(runs: Any, sha: str) -> Optional[dict]:
    """The newest workflow run for this commit (gh run list returns newest first)."""
    for run_info in runs if isinstance(runs, list) else []:
        if str(run_info.get("headSha") or "").lower() == sha.lower():
            return run_info
    return None


def default_pr_body(subjects: list) -> str:
    changes = "\n".join(f"- {subject}" for subject in subjects) or "- (see commits)"
    return (
        "Shipped with the `ship-it` skill.\n\n"
        f"**Changes**\n{changes}\n\n"
        "The deploy workflow builds a live preview of this pull request; "
        "its URL appears on this pull request when it is ready."
    )


# --- Processes, git and GitHub -------------------------------------------------------


def tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ShipError(f"'{name}' is not on PATH. Install it and try again.")
    return path


def run(
    args: list,
    cwd: Path,
    check: bool = True,
    capture: bool = True,
    input_text: Optional[str] = None,
) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        [str(arg) for arg in args],
        cwd=str(cwd),
        input=input_text,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        detail = ((proc.stderr or "") + (proc.stdout or "")).strip() if capture else ""
        command = " ".join([Path(str(args[0])).stem] + [str(arg) for arg in args[1:]])
        raise ShipError(f"`{command}` failed" + (f": {detail}" if detail else f" (exit {proc.returncode})"))
    return proc


def gh_json(gh: str, root: Path, *args: str) -> Any:
    proc = run([gh, *args], root, check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def fetch_json(url: str, timeout: float = 15.0) -> Any:
    request = urllib.request.Request(url, headers={"Cache-Control": "no-cache", "User-Agent": "ship-it"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as error:
        # Some Python installs (e.g. python.org builds on macOS) lack CA certificates; curl has them.
        if isinstance(getattr(error, "reason", None), ssl.SSLError):
            return fetch_json_with_curl(url, timeout)
        return None
    except (ssl.SSLError, OSError, ValueError):
        return None


def fetch_json_with_curl(url: str, timeout: float) -> Any:
    curl = shutil.which("curl")
    if not curl:
        return None
    proc = subprocess.run(
        [curl, "-fsSL", "--max-time", str(int(timeout)), "-H", "Cache-Control: no-cache", url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def find_root() -> Path:
    proc = subprocess.run([tool("git"), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise ShipError("Not inside a git repository. Run ship-it from your project folder.")
    return Path(proc.stdout.strip())


# --- The procedure -----------------------------------------------------------------------


def ship(args: argparse.Namespace) -> int:
    root = find_root()
    git, gh = tool("git"), tool("gh")

    def g(*git_args: str, **kwargs: Any) -> subprocess.CompletedProcess:
        return run([git, *git_args], root, **kwargs)

    if run([gh, "auth", "status"], root, check=False).returncode != 0:
        raise ShipError("GitHub CLI is not signed in. Run `gh auth login` and try again.")

    info = gh_json(gh, root, "repo", "view", "--json", "nameWithOwner,defaultBranchRef")
    if not info:
        raise ShipError("Could not read the GitHub repository for this folder (gh repo view failed).")
    repo = info["nameWithOwner"]
    default_branch = (info.get("defaultBranchRef") or {}).get("name") or "main"

    current = g("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    dirty = bool(g("status", "--porcelain").stdout.strip())
    on_protected = is_protected(current, default_branch)
    test_command = shlex.split(args.test_command or "")
    if not test_command:
        raise ShipError("A test command is required (default: npm test).")

    if args.dry_run:
        new_branch = args.branch or feature_branch_name(args.title or args.message or "change")
        steps = [
            f"run tests: {args.test_command}",
            f"branch: create {new_branch} from {current}" if on_protected else f"branch: stay on {current}",
            ("commit: " + (" ".join(args.paths) if args.paths else "all changes")) if dirty else "commit: nothing to commit",
            f"push: {args.remote} (never forced, never to {default_branch})",
            f"pull request: open or update against {default_branch} in {repo}",
            "wait: skipped" if args.no_wait else f"wait: up to {args.timeout}s for the preview of this commit",
        ]
        for step in steps:
            log(f"[dry run] {step}")
        return 0

    log(f"Running `{args.test_command}` ...")
    test_command[0] = tool(test_command[0])
    if run(test_command, root, check=False, capture=False).returncode != 0:
        raise ShipError("Tests failed. Fix them and run ship-it again; nothing was committed or pushed.", code=1)
    log("Tests passed.")

    log(f"Fetching {args.remote}/{default_branch} ...")
    g("fetch", "--quiet", args.remote, default_branch)
    base_ref = f"{args.remote}/{default_branch}"

    if on_protected:
        ahead = int(g("rev-list", "--count", f"{base_ref}..HEAD").stdout.strip() or "0")
        if not dirty and ahead == 0:
            raise ShipError(f"Nothing to ship: no changes and no commits beyond {default_branch}.")
        if args.branch and is_protected(args.branch, default_branch):
            raise ShipError(f"Refusing to ship to '{args.branch}': use a feature branch.")
        wanted = args.branch or feature_branch_name(args.title or args.message or "change")
        existing = set(g("for-each-ref", "--format=%(refname:short)", "refs/heads").stdout.split())
        for ref in g("for-each-ref", "--format=%(refname:short)", f"refs/remotes/{args.remote}").stdout.split():
            if "/" in ref:
                existing.add(ref.split("/", 1)[1])
        branch = unique_branch(wanted, existing)
        g("switch", "--create", branch)
        log(f"Created branch {branch} (you were on {current}); your changes came along.")
    else:
        branch = current
        if args.branch and args.branch != branch:
            log(f"Already on feature branch {branch}; ignoring --branch {args.branch}.")

    if dirty:
        if not args.message:
            raise ShipError('There are uncommitted changes: pass --message "<commit subject>" to commit them.')
        if args.paths:
            g("add", "--", *args.paths)
        else:
            g("add", "--all")
        staged = g("diff", "--cached", "--name-only").stdout.split()
        if staged:
            g("commit", "--quiet", "--file", "-", input_text=args.message.strip() + "\n")
            log(f"Committed {len(staged)} file(s): {args.message.strip().splitlines()[0]}")
        else:
            log("Nothing staged to commit (only ignored or unselected files changed).")

    ahead = int(g("rev-list", "--count", f"{base_ref}..HEAD").stdout.strip() or "0")
    if ahead == 0:
        raise ShipError(f"Nothing to ship: {branch} has no commits beyond {default_branch}.")
    if is_protected(branch, default_branch):
        raise ShipError(f"Refusing to push to {branch}.")

    log(f"Pushing {branch} to {args.remote} ...")
    push = g("push", "--set-upstream", args.remote, branch, check=False)
    if push.returncode != 0:
        detail = (push.stderr or push.stdout or "").strip()
        raise ShipError(
            "Push failed (git's message is below). ship-it never force-pushes: if the branch moved on "
            f"GitHub, pull or rebase it yourself and run ship-it again.\n{detail}"
        )
    head_sha = g("rev-parse", "HEAD").stdout.strip()

    pr = gh_json(gh, root, "pr", "view", branch, "--json", "number,url,state")
    if pr and pr.get("state") == "OPEN":
        edits = []
        if args.title:
            edits += ["--title", args.title]
        if args.body:
            edits += ["--body", args.body]
        if edits:
            run([gh, "pr", "edit", str(pr["number"]), *edits], root)
        log(f"Updated pull request #{pr['number']}: {pr['url']}")
    else:
        subjects = g("log", "--format=%s", f"{base_ref}..HEAD").stdout.strip().splitlines()
        title = args.title or (subjects[0] if subjects else branch)
        command = [gh, "pr", "create", "--base", default_branch, "--head", branch, "--title", title]
        command += ["--body", args.body or default_pr_body(subjects)]
        if args.draft:
            command.append("--draft")
        run(command, root)
        pr = gh_json(gh, root, "pr", "view", branch, "--json", "number,url,state")
        if not pr:
            raise ShipError("The pull request was created but could not be read back (gh pr view failed).")
        log(f"Opened pull request #{pr['number']}: {pr['url']}")

    if args.no_wait:
        print(f"PR_URL={pr['url']}")
        return 0

    url, outcome = wait_for_preview(gh, root, repo, pr["number"], branch, head_sha, args)
    print(f"PR_URL={pr['url']}")
    if outcome == "verified":
        log(f"Preview is live and serves {head_sha[:7]}.")
        print(f"PREVIEW_URL={url}")
        return 0
    known = f" Last known preview URL: {url}." if url else ""
    log(f"Preview not verified within {args.timeout}s.{known} Run the same command again to keep waiting.")
    return 3


def wait_for_preview(
    gh: str,
    root: Path,
    repo: str,
    pr_number: int,
    branch: str,
    head_sha: str,
    args: argparse.Namespace,
) -> tuple:
    log(f"Waiting up to {args.timeout}s for the preview of {head_sha[:7]} ...")
    deadline = time.monotonic() + args.timeout
    url: Optional[str] = None
    last_message = ""
    succeeded_without_url_at: Optional[float] = None
    while True:
        statuses = gh_json(gh, root, "api", f"repos/{repo}/commits/{head_sha}/statuses")
        comments = gh_json(gh, root, "api", f"repos/{repo}/issues/{pr_number}/comments?per_page=100")
        url = find_preview_url(statuses, comments) or url
        if url:
            payload = fetch_json(f"{url}/hub.json?ship-it={int(time.time())}")
            if hub_reports_sha(payload, head_sha):
                return url, "verified"
            message = f"Preview {url} is up but still serves {reported_sha(payload)}; waiting ..."
        else:
            message = "Waiting for the deploy workflow to publish the preview URL ..."

        runs = gh_json(
            gh, root, "run", "list", "--repo", repo, "--workflow", args.workflow, "--branch", branch,
            "--json", "status,conclusion,headSha,url", "--limit", "20",
        )
        run_info = latest_run_for(runs, head_sha)
        if run_info:
            status = run_info.get("status") or ""
            conclusion = run_info.get("conclusion") or ""
            if conclusion in FAILED_CONCLUSIONS:
                raise ShipError(f"The deploy workflow ended with '{conclusion}': {run_info.get('url')}", code=3)
            if "action_required" in (status, conclusion) or status == "waiting":
                message = f"The deploy workflow is waiting for approval: {run_info.get('url')}"
            elif status == "completed" and conclusion == "success" and not url:
                succeeded_without_url_at = succeeded_without_url_at or time.monotonic()
                if time.monotonic() - succeeded_without_url_at > NO_PREVIEW_GRACE_SECONDS:
                    raise ShipError(
                        "The deploy workflow succeeded but published no preview URL. Is the "
                        "AZURE_STATIC_WEB_APPS_API_TOKEN repository secret set? "
                        f"See {run_info.get('url')}",
                        code=3,
                    )

        if message != last_message:
            log(message)
            last_message = message
        if time.monotonic() >= deadline:
            return url, "timeout"
        time.sleep(max(1, args.interval))


def parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test, commit to a feature branch, push, open or update the PR, and wait for its preview.",
    )
    parser.add_argument("-m", "--message", help="commit message for uncommitted changes (subject line first)")
    parser.add_argument("--title", help="pull request title (default: the first commit subject)")
    parser.add_argument("--body", help="pull request body (default: the list of commits)")
    parser.add_argument("--branch", help="branch to create when on the default branch (default: feat/<slug>)")
    parser.add_argument("--paths", nargs="+", help="commit only these paths (default: every change git does not ignore)")
    parser.add_argument("--draft", action="store_true", help="open the pull request as a draft")
    parser.add_argument("--remote", default="origin", help="git remote to push to (default: origin)")
    parser.add_argument("--test-command", default="npm test", help="command that must pass first (default: npm test)")
    parser.add_argument("--workflow", default="deploy.yml", help="workflow file that deploys previews (default: deploy.yml)")
    parser.add_argument("--timeout", type=int, default=300, help="seconds to wait for the preview (default: 300)")
    parser.add_argument("--interval", type=int, default=10, help=argparse.SUPPRESS)
    parser.add_argument("--no-wait", action="store_true", help="open or update the PR without waiting for the preview")
    parser.add_argument("--dry-run", action="store_true", help="print the plan without changing anything")
    return parser.parse_args(argv)


def main(argv: Optional[list] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    args = parse_args(argv)
    try:
        return ship(args)
    except ShipError as error:
        log(f"STOPPED: {error}")
        return error.code
    except KeyboardInterrupt:
        log("Interrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
