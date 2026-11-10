# Skill detail pages

Status: Decisions captured after five question rounds. Implementation authorized
by the subsequent request to implement this document and open a review preview.

## Problem

The hub's catalog cards provide brief descriptions and links, but visitors cannot
open a skill in the hub to understand its purpose, usage guidance, provenance,
and full instructions. External recommendations have metadata and links, but
their skill files are not stored in this repository.

## User value

Visitors can decide whether a skill fits their task, understand where it comes
from, inspect local instructions before installing, and share a direct link to
the skill without leaving the hub for basic information.

## Requirements

- Give every local skill and external recommendation a detail page.
- Use the existing description for "What it does" and add short, explicitly
  curated "When to use" guidance for every skill in the catalog sources. Do not
  generate guidance at runtime.
- Show the complete local `SKILL.md`, including YAML frontmatter, as escaped
  plain text. Identify it as this hub's build-time copy, not a live upstream file.
- For external skills, explain that the full file is not hosted here and link
  upstream. Do not fetch or copy external skill files in this release.
- Show local/external status, credited source, license information, and a clearly
  labeled repository or upstream link. Distinguish the credited origin from the
  repository supplying the displayed local file. Do not invent origin URLs or
  stronger license claims than the catalog provides.
- Retain install-command copying and context footprints where already available.
- Keep supporting files accessible through source links, without an embedded
  file browser.

## UX decisions

- Use shareable routes at `/skills/<name>`. Skill names are unique across local
  and external entries; do not include a kind segment in the route.
- Link card titles to their detail pages. Keep install/copy and source actions
  separate from navigation.
- Preserve catalog search and filter state when returning with browser Back.
- Show a clear not-found state for unknown skill names.
- Present the complete local file in a clearly labeled, wrapping code block,
  rather than rendered Markdown. Do not add a Markdown renderer.
- Preserve the hub's accessible, responsive presentation, including visible
  focus, semantic structure, and usability at 360px wide.
- Keep the environment badge (`#build-badge`) and demo footer notice visible on
  detail and not-found views.

## Acceptance criteria

- Every catalog card title opens the matching `/skills/<name>` page, and that
  URL also works when opened directly or refreshed.
- Every detail page displays the skill title, existing description, curated
  usage guidance, status, provenance, and license information.
- A local detail page displays the complete build-time `SKILL.md`, including
  frontmatter, without interpreting its contents as HTML or Markdown.
- An external detail page clearly indicates that its full file is not hosted
  in the hub and provides its upstream link without fetching the external file.
- Credited origin and the hub copy are distinguishable; source links provide
  access to supporting files where present.
- Install-command copying still works, and existing context footprint data
  remains visible where available.
- Returning to the catalog with browser Back restores its search and filters.
- An unknown skill route displays a clear not-found state rather than a blank
  page or an unrelated skill.
- Detail and not-found views remain keyboard-accessible and usable at 360px
  wide, with the environment badge and demo notice visible.
- Implementation stays within the static HTML/CSS/vanilla JavaScript and
  standard-library Python build. Generated catalog data comes from source
  files, not manual edits to `site/hub.json`.
- Before implementation is considered complete, updated focused tests pass
  with `npm test`, and HTTP checks verify direct routes and required assets.
  Any temporary server is stopped afterward.

## Open questions

No product-scope questions remain from the five rounds. Exact curated usage
wording and visual layout are not yet authored; they must follow these decisions.
No further product-scope confirmation is required for this implementation.
