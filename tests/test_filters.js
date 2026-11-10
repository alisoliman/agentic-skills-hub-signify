const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = readFileSync(path.join(__dirname, "../site/app.js"), "utf8");

function filterCards(filters) {
  const cards = [
    { dataset: { kind: "local", search: "grilling demo planning", tags: '["demo","planning"]' } },
    { dataset: { kind: "local", search: "foundry reference content for this demo", tags: '["reference"]' } },
    { dataset: { kind: "external", search: "external demo-tools", tags: '["demo-tools"]' } },
  ];
  const count = { textContent: "" };
  const empty = { hidden: true };
  const context = vm.createContext({
    URLSearchParams,
    history: { replaceState() {} },
    location: { hash: "" },
    document: {
      querySelector(selector) {
        return { "#result-count": count, "#empty-state": empty }[selector];
      },
      querySelectorAll(selector) {
        if (selector === ".skill-title-link") return [];
        assert.equal(selector, ".skill-card");
        return cards;
      },
    },
    // Keep bootstrap pending while exercising the synchronous filter behavior.
    fetch: () => new Promise(() => {}),
    filters,
  });
  vm.runInContext(source, context);
  vm.runInContext("Object.assign(state, filters); applyFilters();", context);
  return { visible: cards.filter((card) => !card.hidden), count: count.textContent, empty: !empty.hidden };
}

test("tags match exact tag values, not descriptions or longer tag names", () => {
  const result = filterCards({ activeTag: "demo" });
  assert.equal(result.visible.length, 1);
  assert.equal(result.visible[0].dataset.search, "grilling demo planning");
  assert.equal(result.count, "1 skill");
  assert.equal(result.empty, false);
});

test("search, kind, and tag filters combine", () => {
  const result = filterCards({ query: " DEMO ", activeKind: "external", activeTag: "demo-tools" });
  assert.equal(result.visible.length, 1);
  assert.equal(result.visible[0].dataset.kind, "external");
  assert.equal(filterCards({ query: "demo" }).visible.length, 3);
});

test("empty and unfiltered states report accurate counts", () => {
  const empty = filterCards({ query: "no-such-skill" });
  assert.equal(empty.visible.length, 0);
  assert.equal(empty.count, "0 skills");
  assert.equal(empty.empty, true);
  const all = filterCards({});
  assert.equal(all.visible.length, 3);
  assert.equal(all.count, "3 skills");
  assert.equal(all.empty, false);
});
