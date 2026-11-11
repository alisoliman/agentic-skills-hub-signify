# Skill detail pages

**Status:** Product scope agreed.

## Problem

The catalog cards provide a short summary and source link, but do not give visitors a focused place to understand a skill's purpose, usage guidance, provenance, and full instructions.

## User value

Visitors can decide whether a skill fits their task, understand when it should be used and where it came from, and read local skill instructions without leaving the hub.

## Requirements

- Provide a detail page for every catalog skill at `/skills/<name>`. Pages must work when opened directly and be shareable.
- Link each skill card to its detail page and provide a clear return path to the catalog.
- Show the existing catalog description as **What it does**.
- For local skills, show the description from the source `SKILL.md` frontmatter as **When to use**. Do not add a separately curated field.
- Show provenance using the existing local/external kind, source label, license, and source URL.
- Include the complete local `skills/<name>/SKILL.md` file as rendered Markdown.
- For external skills, show their existing catalog metadata and refer visitors to the upstream source. Do not copy external skill files into the hub.
- Retain the install command and its copy action on the detail page.
- Keep the implementation compatible with the static HTML/CSS/vanilla JavaScript site. Do not add a framework or dependency.
- Keep assets root-absolute, and keep the build badge and demo notice visible on detail pages. Preserve semantic markup, visible keyboard focus, and responsiveness down to 360px.
- Add local skill file content through the catalog build source; never edit generated `site/hub.json` directly.

## UX decisions

- **Navigation:** Use a dedicated path-based page, `/skills/<name>`, rather than a modal or inline card expansion.
- **Usage guidance:** Reuse existing descriptions: the catalog summary for what the skill does, and local `SKILL.md` frontmatter for when to use it.
- **External content:** Link to the external source instead of embedding or copying its full file.
- **Full file:** Render the complete local skill file as Markdown. Prefer a safe, dependency-free renderer.
- **Provenance:** Display kind, source, license, and a link to the source.
- **Existing action:** Keep the install command available and copyable.

## Acceptance criteria

1. Selecting a skill opens its `/skills/<name>` page; loading that URL directly works, and the page has a clear link back to the catalog.
2. A local skill page shows its catalog summary, frontmatter usage guidance, provenance, source link, install command, and complete `SKILL.md` rendered as Markdown.
3. An external skill page shows its available catalog metadata and source link, and directs visitors to that source for the full skill file.
4. The Markdown view preserves the full local file, including its frontmatter and the Markdown structures used by the current skills.
5. Unknown skill names produce a clear not-found state with a way back to the catalog.
6. Detail pages retain the environment badge and demo notice, and remain keyboard-accessible and usable at 360px wide.
7. Build and HTTP checks verify generated content and direct access to a detail route.

## Implementation notes

- The dependency-free renderer supports the Markdown structures used by the current local skill files: headings, paragraphs, lists, tables, blockquotes, inline formatting and links, and fenced code blocks. Raw HTML is displayed as text.
- Relative links in local skill files point to the corresponding file in the upstream repository.
- YAML frontmatter remains visible as a YAML block above the rendered Markdown body.

## Open questions

- If future skill files use Markdown features outside the current supported subset, should the renderer expand to cover them or adopt a full CommonMark/GFM implementation?
