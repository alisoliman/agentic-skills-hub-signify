const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = readFileSync(path.join(__dirname, "../site/app.js"), "utf8");

class Element {
  constructor(tag) {
    this.tag = tag;
    this.attributes = {};
    this.dataset = {};
    this.children = [];
    this.textContent = "";
    this.style = {
      setProperty(name, value) {
        this[name] = value;
      },
    };
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  removeAttribute(name) {
    delete this.attributes[name];
  }

  append(...children) {
    this.children.push(...children);
  }

  addEventListener() {}
}

function loadApp() {
  const elements = {};
  const context = vm.createContext({
    document: {
      createElement: (tag) => new Element(tag),
      querySelector: (selector) => elements[selector] || null,
      querySelectorAll: () => [],
      documentElement: new Element("html"),
    },
    // Keep bootstrap pending; these tests call the render helpers directly.
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(source, context);
  return { context, elements };
}

function textOf(node) {
  return [node.textContent, ...node.children.map(textOf)].join(" ");
}

const foundry = {
  name: "microsoft-foundry",
  title: "Microsoft Foundry",
  description: "Deploy and evaluate agents.",
  tags: ["azure"],
  kind: "local",
  agentSkill: false,
  license: "MIT",
  source: "Microsoft",
  url: "https://github.com/octo-org/hub/tree/main/skills/microsoft-foundry",
  installCommand: "gh skill install octo-org/hub microsoft-foundry",
  footprint: { indexTokens: 180, bodyTokens: 1234, files: 87, fileTokens: 182345 },
};

test("local cards show the context footprint and the gh skill install command", () => {
  const { context } = loadApp();
  context.skill = foundry;
  const card = vm.runInContext("createCard(skill, 0)", context);
  const text = textOf(card);
  assert.match(text, /Context footprint · est\. tokens/);
  assert.match(text, /Always\s+~180/);
  assert.match(text, /On use\s+~1\.2k/);
  assert.match(text, /Files\s+87 · ~182k/);
  assert.match(text, /gh skill install octo-org\/hub microsoft-foundry/);
  assert.equal(card.dataset.tags, '["azure"]');
});

test("external cards have no footprint and project skills are labelled", () => {
  const { context } = loadApp();
  context.skill = { ...foundry, kind: "external", footprint: undefined };
  assert.doesNotMatch(textOf(vm.runInContext("createCard(skill, 0)", context)), /Context footprint/);
  context.skill = { ...foundry, name: "ship-it", agentSkill: true };
  assert.match(textOf(vm.runInContext("createCard(skill, 0)", context)), /local · project skill/);
});

test("token counts are formatted compactly", () => {
  const { context } = loadApp();
  const format = (count) => vm.runInContext(`formatTokens(${count})`, context);
  assert.equal(format(0), "0");
  assert.equal(format(999), "999");
  assert.equal(format(1000), "1k");
  assert.equal(format(1234), "1.2k");
  assert.equal(format(9990), "10k");
  assert.equal(format(182345), "182k");
});

test("the hero install command uses the featured local skill", () => {
  const { context } = loadApp();
  const skills = "[{ kind: 'local', name: 'grilling', installCommand: 'gh skill install o/r grilling' }]";
  assert.equal(
    vm.runInContext(`featuredInstallCommand({ repo: 'o/r', featuredSkill: 'grilling' }, ${skills})`, context),
    "gh skill install o/r grilling",
  );
  assert.equal(vm.runInContext("featuredInstallCommand({ repo: 'o/r' }, [])", context), "gh skill install o/r grilling");
});

test("the environment badge shows the build and links to the commit or pull request", () => {
  const { context, elements } = loadApp();
  const badge = new Element("a");
  elements["#build-badge"] = badge;

  vm.runInContext(
    "state.config = { repo: 'o/r' };" +
      "state.build = { env: 'preview', pr: 3, sha: 'abcdef1234', label: 'Preview · PR #3 · abcdef1' };" +
      "renderBuildBadge();",
    context,
  );
  assert.equal(badge.textContent, "Preview · PR #3 · abcdef1");
  assert.equal(badge.dataset.env, "preview");
  assert.equal(badge.attributes.href, "https://github.com/o/r/pull/3");

  vm.runInContext("state.build = { env: 'production', sha: 'abcdef1234', label: 'Production · abcdef1' }; renderBuildBadge();", context);
  assert.equal(badge.attributes.href, "https://github.com/o/r/commit/abcdef1234");

  vm.runInContext("state.build = null; renderBuildBadge();", context);
  assert.equal(badge.textContent, "Local build");
  assert.equal(badge.dataset.env, "local");
  assert.equal(badge.attributes.href, undefined);
});

test("theme colors become CSS custom properties", () => {
  const { context } = loadApp();
  vm.runInContext("applyTheme({ accent: '#0f6cbd', ink: '#ffffff', link: '#0d5ea6' })", context);
  const style = context.document.documentElement.style;
  assert.equal(style["--accent"], "#0f6cbd");
  assert.equal(style["--accent-ink"], "#ffffff");
  assert.equal(style["--link"], "#0d5ea6");
});
