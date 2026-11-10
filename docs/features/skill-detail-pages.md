# Skill detail pages

Status: Decisions agreed after two grilling rounds; implementation subsequently
authorized. The implementation follows the decisions below.

## Problem

The hub currently presents skills as catalog cards without detail pages.
Visitors can see descriptions, install commands, and source links, but cannot
consistently understand a skill's purpose, appropriate use, limitations, or
provenance before choosing it.

The catalog does not currently have dedicated fields for usage guidance,
limitations, or authors, and does not expose full skill instructions.

## User value

Prioritize newcomers discovering skills. A visitor should be able to answer:
"Does this solve my task, and when should I avoid it?"

Explain outcomes and limitations rather than just listing capabilities. Make
source inspection and the existing installation action available without
turning the page into an installation tutorial.

## Requirements

- Provide a detail page for every local and external catalog skill.
- Include "What it does," "When to use it," "When not to use it," and one
  example task using curated, evidence-supported guidance.
- Show the canonical source link and author or publisher when known. Keep
  attribution separate from trust; do not imply that a skill is official,
  verified, or safe without supporting evidence.
- Explicitly label missing usage guidance or attribution rather than inventing
  it. Incomplete information does not block publication of a detail page.
- Identify demo-authored guidance as such.
- Display the existing install command unchanged with its copy button.
  Do not add a new installation workflow or tutorial.
- Keep full skill instructions at the source link, rather than embedding them.
- Retain existing catalog card install and source controls.
- Keep content demo-only, with no customer data, credentials, or customer code.

## UX decisions

- Use shareable pages at `/skills/<stable-id>`, not temporary overlays.
- Link card titles to their corresponding detail pages.
- Provide a clear return-to-catalog link and preserve catalog filters when
  returning.
- Lead with purpose and decision-making guidance; make source attribution and
  installation easy to find.
- Provide accessible copy success and failure feedback.
- Keep the environment badge (`#build-badge`) and demo footer notice visible
  on every detail page.
- Use root-absolute asset and data paths.
- Support keyboard navigation, visible focus, semantic HTML, appropriate
  labels, WCAG AA contrast, and responsive layouts down to 360px.

## Acceptance criteria

- Every local and external catalog skill has a unique, stable detail URL that
  works when opened directly and refreshed on Azure and with `npm start`.
- Selecting a catalog card title opens the correct skill's detail page.
- A visitor can understand the skill's purpose, appropriate use, limitations,
  and an example task, or see explicit notices where guidance is unavailable.
- Provenance links to the canonical source; known attribution is shown,
  unknown attribution is labeled, and no unsupported endorsement is implied.
- Demo-authored guidance is clearly distinguished from source information.
- The displayed install command matches the existing catalog command exactly;
  copying places that command on the clipboard and reports success or failure
  accessibly.
- Existing catalog install and source controls continue to work.
- Returning to the catalog preserves the visitor's filters.
- All interactions work with a keyboard, focus is visible, and content remains
  readable and usable at 360px wide with WCAG AA contrast.
- Every detail page visibly includes the environment badge and demo notice.
- Implementation adds focused tests for the new behavior and passes the
  existing `npm test` checks.

## Open questions

No product or UX questions remain from the agreed two-round session.

Implementation details resolved:

- Existing skill names are stable IDs, independent of titles and kinds. The
  build rejects duplicates across local/external entries and names that are
  not lowercase URL-safe slugs. Keep names unchanged when editing titles.
- Curated guidance and attribution live under `details` in
  `catalog/local-skills.json` and `catalog/external-skills.json`. Maintainers
  update these alongside source changes; the build validates text and HTTPS
  source links. Missing fields remain empty and the UI explicitly labels them.
- Local canonical links point to the checked-in `SKILL.md`. External canonical
  links are recorded only where identified; the GitHub CLI entry retains its
  catalog source link because its file is absent from the current upstream
  repository. Source attribution is not safety verification.
- Native page navigation uses the existing Azure/local index fallback.
  Search, kind, and tag filters travel in URL query parameters, including the
  detail page's return link; no browser storage or dependencies are needed.
