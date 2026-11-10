# Copilot instructions

This repository is an Agentic Skills Hub: a small static site that catalogs agent skills for a GitHub Innovation Series demo. Everything in it is demo content.

## Stack

- `site/`: static HTML, CSS and vanilla JavaScript. No frameworks, bundlers or npm dependencies; do not add any unless the user asks.
- `scripts/build_catalog.py` (Python standard library) generates `site/hub.json` from `skills/*/SKILL.md` and `catalog/*.json`. Never edit `site/hub.json`; change the sources and run `npm run build`.
- Skills live in `skills/<name>/`. The build copies the ones listed in `agentSkills` (`catalog/config.json`) to `.github/skills/<name>/`: edit `skills/`, never the copies.
- `.github/workflows/deploy.yml` deploys to Azure Static Web Apps: `main` is production and every pull request gets its own preview URL.

## Working rules

- Run `npm test` before you finish, and add or update tests in `tests/` for new behavior.
- Verify behavior with `npm test` and HTTP checks (for example `curl` against `npm start -- --port <free port>`). Do not use computer-use, desktop or browser automation tools, and stop any server you start before you finish.
- Use root-absolute paths for assets and data (`/styles.css`, `/hub.json`). Path-based routes work on Azure and with `npm start`.
- Keep pages accessible (semantic HTML, labels, visible focus, WCAG AA contrast) and responsive down to 360px wide.
- Keep the environment badge (`#build-badge`) and the demo notice in the footer visible on every page.
- Demo content only: no customer data, credentials or customer source code.
- To publish work for review, use the `ship-it` skill. Never push to `main` and never merge pull requests yourself.
