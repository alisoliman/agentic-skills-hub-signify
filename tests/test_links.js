const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class Element {
  constructor(tag) {
    this.tag = tag;
    this.attributes = {};
    this.dataset = {};
    this.children = [];
  }

  setAttribute(name, value) {
    this.attributes[name] = value;
  }

  append(...children) {
    this.children.push(...children);
  }

  addEventListener() {}
}

test("source links navigate in the current tab without requiring a popup", () => {
  const context = vm.createContext({
    document: { createElement: (tag) => new Element(tag) },
    // Isolate card rendering from the asynchronous catalog request.
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(readFileSync(path.join(__dirname, "../site/app.js"), "utf8"), context);
  for (const kind of ["local", "external"]) {
    const url = "https://github.com/octo-org/agentic-skills-hub/tree/main/skills/grilling";
    context.skill = { name: "grilling", title: "Grilling", description: "Interview", tags: [], kind, url };
    const card = vm.runInContext("createCard(skill, 0)", context);
    const anchors = card.children.flatMap((child) => child.children).filter((child) => child.tag === "a");
    assert.equal(anchors.length, 2);
    const detail = anchors.find((anchor) => anchor.attributes.href === "/skills/grilling");
    const source = anchors.find((anchor) => anchor.textContent === "Source");
    assert.ok(detail);
    assert.equal(detail.attributes.target ?? "_self", "_self");
    assert.ok(source);
    assert.equal(source.attributes.href, url);
    assert.equal(source.attributes.target ?? "_self", "_self");
    assert.equal(source.attributes.rel, "noreferrer");
  }
});
