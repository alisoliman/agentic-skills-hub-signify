# Signify Agentic Skills Hub

A small, deployed catalog of agent skills: find a skill, install it with one command, and improve it with your team. It is the demo project for the GitHub Innovation Series session on agentic skills, where GitHub Copilot extends this hub live using skills.

Everything here is demo content. It is not an official registry, package index or production system.

## What's inside

| Path | What it is |
| --- | --- |
| `site/` | The static site: `index.html`, `styles.css` and `app.js` (vanilla JavaScript, no build step) |
| `scripts/build_catalog.py` | Generates `site/hub.json` from the skills and catalog files (Python standard library) |
| `skills/<name>/` | The canonical skills, each with a `SKILL.md` and its supporting files |
| `.github/skills/<name>/` | Copies of the agent skills Copilot uses in this repository, refreshed by the build |
| `catalog/` | Hub settings (`config.json`), display metadata for local skills, external recommendations |
| `.github/copilot-instructions.md` | Always-on instructions for Copilot in this repository |
| `.github/workflows/deploy.yml` | Tests, then deploys `main` to production and each pull request to its own preview |
| `infra/`, `azure.yaml` | Azure Static Web Apps (Free plan), provisioned with the Azure Developer CLI |
| `tests/` | Python and Node tests, run with `npm test` |

## Quickstart (macOS, Linux and Windows)

You need Git, Node.js 18+ and Python 3.9+. There is nothing to install: the project has no dependencies.

```bash
npm run build   # generate site/hub.json and refresh .github/skills
npm test        # Python and Node tests
npm start       # build, then serve the site on http://127.0.0.1:8000
```

The npm scripts find Python for you (`python3`, `python` or the Windows `py -3` launcher). `npm start` listens on 127.0.0.1 only and, like production, serves unknown paths without a file extension with `index.html`, so path-based routes work locally. If port 8000 is busy, run `python3 scripts/serve.py --port 8001` (Windows: `py -3 scripts/serve.py --port 8001`).

For live reload while editing, install [uv](https://docs.astral.sh/uv/) and run `npm run dev` (it serves on http://127.0.0.1:8000 and rebuilds when skills or catalog files change).

`site/hub.json` is generated and ignored by Git: never edit it by hand.

## How it is deployed

The hub is a static site on Azure Static Web Apps. `.github/workflows/deploy.yml` runs `npm test`, builds `hub.json` with build metadata, and deploys:

| Event | Result | Badge in the page header |
| --- | --- | --- |
| Push to `main` | Production | `Production · <sha>` |
| Pull request opened or updated | A preview URL for that pull request: the Static Web Apps bot comments it on the pull request, and the workflow also publishes it as the `hub/preview` commit status | `Preview · PR #<n> · <sha>` |
| Pull request closed | Its preview is deleted | |
| Running locally | Nothing is deployed | `Local build` |

The Free plan allows three previews at a time, so close pull requests you no longer need.

The workflow needs one repository secret, `AZURE_STATIC_WEB_APPS_API_TOKEN`: the deployment token of your Static Web App. Without it, tests still run and the deploy is skipped with a notice. To host your own copy (bash or PowerShell):

```bash
azd env new <environment-name> --location westeurope
azd provision
az staticwebapp secrets list --name "$(azd env get-value SERVICE_WEB_NAME)" --query properties.apiKey -o tsv | gh secret set AZURE_STATIC_WEB_APPS_API_TOKEN
gh workflow run deploy.yml
```

`site/staticwebapp.config.json` sets security headers, `Cache-Control: no-cache` (a refresh always shows the latest deploy) and a navigation fallback, so a page served from a path such as `/skills/grilling` still loads.

## Skills

### Layout

- Canonical skills live in `skills/<name>/` with their supporting files and license. The hub lists them and they can be installed from this repository.
- The skills named in `agentSkills` in `catalog/config.json` are also copied to `.github/skills/<name>/` by `npm run build`, so GitHub Copilot (CLI, VS Code and the Copilot coding agent) uses them as project skills in this repository without any setup. The copies are committed, and a test fails if they drift: edit `skills/`, then run `npm run build`.
- Copilot discovers project skills in `.github/skills`, `.claude/skills` or `.agents/skills`, and personal skills in `~/.copilot/skills` or `~/.agents/skills`.
- `.github/copilot-instructions.md` is always in context; a skill's instructions load only when the skill is used.

| Skill | Agent skill here | Source and license |
| --- | --- | --- |
| `grilling` | Yes | [mattpocock/skills](https://github.com/mattpocock/skills) by Matt Pocock, MIT. `SKILL.md` (design-tree and frontier revision), `agents/openai.yaml` and `LICENSE` are unchanged; provenance is recorded in `skills-lock.json`. |
| `frontend-design` | Yes | [anthropics/skills](https://github.com/anthropics/skills/tree/main/skills/frontend-design) by Anthropic, Apache-2.0 (`LICENSE.txt`), unchanged; recorded in `skills-lock.json`. |
| `ship-it` | Yes | This hub, MIT. Runs the tests, commits to a feature branch, opens or updates the pull request and waits for its preview URL. An example of a skill with a bundled script. |
| `microsoft-foundry` | No, catalog only | Microsoft, MIT. Reference content: using it needs Azure access and the Azure MCP tools. |

External entries in `catalog/external-skills.json` are recommendations, not installed or verified integrations.

### Install a skill from this hub

```bash
gh skill install alisoliman/agentic-skills-hub-signify grilling
```

The GitHub CLI skill commands are in preview: `gh skill preview <owner/repo> <skill>` shows a skill before installing it, and `gh skill search <term>` finds skills. As an alternative, `npx skills add alisoliman/agentic-skills-hub-signify@grilling` uses the open-source `skills` installer. A private hub requires GitHub access to its repository.

### Add a skill

1. Create `skills/<name>/SKILL.md`. The `name` must match the folder; the `description` is what the agent reads in every session, so say what the skill does and when to use it:

   ```markdown
   ---
   name: my-skill
   description: What this skill does and when to use it.
   license: MIT
   ---

   # My skill

   Step-by-step instructions for the agent.
   ```

2. Optionally add a display title, description, tags, source and license in `catalog/local-skills.json`.
3. To let Copilot use it in this repository, add its name to `agentSkills` in `catalog/config.json`.
4. Run `npm run build` and `npm test`.

Keep third-party licenses and attribution with the files you copy.

### Context footprint

Each local skill card estimates what the skill costs the agent's context (tokens are estimated as characters divided by four):

- **Always**: the name and description, in context in every session so the agent knows the skill exists;
- **On use**: the `SKILL.md` instructions, loaded when the agent decides to use the skill;
- **Files**: supporting files such as references and scripts, read only when the instructions call for them.

`microsoft-foundry` shows the point well: a short index entry, and a large payload that stays out of context until it is needed.

## Configure the hub

`catalog/config.json`:

| Field | Purpose |
| --- | --- |
| `customer` | Customer name; empty for the generic template |
| `eyebrow`, `title`, `tagline`, `primaryCta` | Header copy |
| `owner` | Team shown as the catalog owner |
| `repo` | `owner/name` of this repository, used for install commands and links |
| `hubUrl` | Production URL of the hub |
| `featuredSkill` | Skill whose install command is shown in the header |
| `theme.accent` | Brand color for buttons, active filters and focus rings |
| `theme.ink` | Optional text color on the accent; by default white or near-black, whichever has more contrast |
| `agentSkills` | Skills copied to `.github/skills` |
| `notice` | Optional footer text; by default it says the hub is demo content and not an official system |

Links are darkened automatically when the accent is too light to read on the page background.

## License

The hub's own code is MIT licensed (see `LICENSE`). Third-party skills keep their own licenses, listed above.
