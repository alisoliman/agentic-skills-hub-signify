const assert = require("node:assert/strict");
const { readdirSync, readFileSync } = require("node:fs");
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
    this.hidden = false;
    this.classList = {
      values: new Set(),
      toggle(name, force) {
        if (force) this.values.add(name);
        else this.values.delete(name);
      },
    };
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

  replaceChildren(...children) {
    this.children = children;
  }

  addEventListener() {}
}

function loadApp(pathname = "/") {
  const elements = {};
  const context = vm.createContext({
    document: {
      createElement: (tag) => new Element(tag),
      createTextNode: (text) => {
        const node = new Element("#text");
        node.textContent = text;
        return node;
      },
      querySelector: (selector) => elements[selector] || null,
      querySelectorAll: () => [],
      documentElement: new Element("html"),
    },
    window: { location: { pathname } },
    // Keep bootstrap pending; these tests call the render helpers directly.
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(source, context);
  return { context, elements };
}

function textOf(node) {
  return [node.textContent, ...node.children.map(textOf)].join(" ");
}

function descendants(node) {
  return [node, ...node.children.flatMap(descendants)];
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

test("skill card titles link to path-based detail pages", () => {
  const { context } = loadApp();
  context.skill = foundry;
  const card = vm.runInContext("createCard(skill, 0)", context);
  const title = card.children.find((child) => child.tag === "h3");
  assert.equal(title.children[0].attributes.href, "/skills/microsoft-foundry");
});

test("cards expose a named article and an explicit path to read the skill", () => {
  const { context } = loadApp();
  context.skill = foundry;
  const card = vm.runInContext("createCard(skill, 2)", context);
  const nodes = descendants(card);
  const title = nodes.find((node) => node.tag === "h3");
  assert.equal(card.attributes["aria-labelledby"], title.attributes.id);
  const readLink = nodes.find((node) => node.tag === "a" && node.textContent === "Read skill");
  assert.equal(readLink.attributes.href, "/skills/microsoft-foundry");
  assert.equal(readLink.attributes["aria-label"], "Read Microsoft Foundry");
  assert.ok(nodes.some((node) => node.tag === "a" && node.textContent === "Source" && node.attributes.href === foundry.url));
});

test("detail navigation connects purpose, usage, content and install to named sections", () => {
  const { context, elements } = loadApp();
  elements["#skill-detail"] = new Element("main");
  context.skill = { ...foundry, usageDescription: "Use when building an agent.", skillFile: "# Guide\nAgent instructions." };
  vm.runInContext("renderSkillPage(skill)", context);
  const nodes = descendants(elements["#skill-detail"]);
  const navigation = nodes.find((node) => node.tag === "nav");
  assert.equal(navigation.attributes["aria-label"], "On this skill page");
  assert.deepEqual(navigation.children.map((link) => link.attributes.href), [
    "#what-it-does", "#when-to-use", "#full-skill-file", "#install",
  ]);
  for (const link of navigation.children) {
    const section = nodes.find((node) => node.tag === "section" && `#${node.attributes.id}` === link.attributes.href);
    assert.ok(section, `${link.attributes.href} must resolve to a section`);
    assert.equal(section.attributes["aria-labelledby"], section.children[0].attributes.id);
  }
  const text = textOf(elements["#skill-detail"]);
  assert.match(text, /Deploy and evaluate agents\./);
  assert.match(text, /Use when building an agent\./);
  assert.match(text, /Agent instructions\./);
  assert.match(text, /Where it comes from/);
  assert.match(text, /gh skill install octo-org\/hub microsoft-foundry/);
});

test("detail routes decode skill names and reject malformed paths", () => {
  const { context } = loadApp();
  const valid = vm.runInContext("routeForPath('/skills/microsoft-foundry')", context);
  assert.equal(valid.type, "skill");
  assert.equal(valid.name, "microsoft-foundry");
  assert.equal(vm.runInContext("routeForPath('/skills/').type", context), "not-found");
  assert.equal(vm.runInContext("routeForPath('/skills/%E0%A4%A').type", context), "not-found");
});

test("detail routes render known skills and a not-found state for unknown names", () => {
  const { context, elements } = loadApp("/skills/grilling");
  elements["#catalog"] = new Element("main");
  elements["#skill-detail"] = new Element("main");
  elements["#hub-hero"] = new Element("header");
  elements["#skip-link"] = new Element("a");
  elements[".primary-action"] = new Element("a");
  elements["meta[name=description]"] = new Element("meta");
  elements["meta[property='og:title']"] = new Element("meta");
  elements["meta[property='og:description']"] = new Element("meta");
  context.config = { title: "Agentic Skills Hub", tagline: "Find and install skills." };
  context.skills = [{
    ...foundry,
    name: "grilling",
    title: "Grilling",
    kind: "local",
    usageDescription: "Use this skill to test a plan.",
    skillFile: "---\nname: grilling\ndescription: Use this skill to test a plan.\n---\n\n# Instructions\nRead carefully.",
  }];
  vm.runInContext("state.config = config; state.skills = skills; renderCurrentPage()", context);

  assert.equal(elements["#catalog"].hidden, true);
  assert.equal(elements["#skill-detail"].hidden, false);
  assert.match(textOf(elements["#skill-detail"]), /What it does/);
  assert.match(textOf(elements["#skill-detail"]), /When to use/);
  assert.match(textOf(elements["#skill-detail"]), /Instructions/);
  assert.equal(elements["#skip-link"].attributes.href, "#skill-detail");
  assert.equal(elements[".primary-action"].attributes.href, "/#catalog");
  assert.ok(elements["#hub-hero"].classList.values.has("detail-mode"));
  assert.equal(context.document.title, "Grilling · Agentic Skills Hub");

  context.window.location.pathname = "/skills/missing";
  vm.runInContext("renderCurrentPage()", context);
  assert.match(textOf(elements["#skill-detail"]), /No skill named “missing” is in this catalog/);
});

test("local skill files render Markdown, retain frontmatter, and block unsafe links", () => {
  const { context } = loadApp();
  const markdown = [
    "---",
    "name: sample",
    "description: Use this skill for a sample task.",
    "---",
    "",
    "# Overview",
    "Use **bold** and `inline code`, plus [the guide](references/guide.md).",
    "",
    "> A useful note.",
    "",
    "- First",
    "  - Nested",
    "",
    "| Topic | Value |",
    "| --- | --- |",
    "| Skill | Full text |",
    "",
    "```js",
    'const html = "<script>";',
    "```",
    "",
    "[unsafe](javascript:alert(1))",
    "<script>not executable</script>",
  ].join("\n");
  const target = new Element("div");
  context.markdown = markdown;
  context.target = target;
  context.skill = foundry;
  vm.runInContext("renderSkillMarkdown(markdown, target, skill)", context);

  const nodes = descendants(target);
  const anchors = nodes.filter((node) => node.tag === "a");
  assert.match(textOf(target), /description: Use this skill for a sample task\./);
  assert.match(textOf(target), /Overview/);
  assert.match(textOf(target), /Nested/);
  assert.match(textOf(target), /Topic/);
  assert.match(textOf(target), /not executable/);
  assert.ok(nodes.some((node) => node.tag === "table"));
  assert.ok(nodes.some((node) => node.tag === "blockquote"));
  assert.ok(nodes.some((node) => node.tag === "strong"));
  assert.ok(nodes.some((node) => node.tag === "code"));
  assert.equal(nodes.filter((node) => node.tag === "script").length, 0);
  assert.equal(anchors[0].attributes.href, "https://github.com/octo-org/hub/blob/main/skills/microsoft-foundry/references/guide.md");
  assert.equal(anchors.some((anchor) => anchor.attributes.href.startsWith("javascript:")), false);
});

test("the renderer processes every checked-in local skill file", () => {
  const { context } = loadApp();
  const skillsDir = path.join(__dirname, "../skills");
  for (const name of readdirSync(skillsDir)) {
    const markdown = readFileSync(path.join(skillsDir, name, "SKILL.md"), "utf8");
    const target = new Element("div");
    context.markdown = markdown;
    context.target = target;
    context.skill = {
      kind: "local",
      url: `https://github.com/alisoliman/agentic-skills-hub-signify/tree/main/skills/${name}`,
    };
    vm.runInContext("renderSkillMarkdown(markdown, target, skill)", context);
    assert.ok(descendants(target).length > 1, `${name} should render its full skill file`);
  }
});

test("external skill detail pages link to the upstream file without embedding it", () => {
  const { context, elements } = loadApp();
  const detail = new Element("main");
  elements["#skill-detail"] = detail;
  context.skill = {
    ...foundry,
    kind: "external",
    package: "octo/skills",
    source: "octo/skills",
    skillFile: undefined,
  };
  vm.runInContext("renderSkillPage(skill)", context);
  const text = textOf(detail);
  const anchors = descendants(detail).filter((node) => node.tag === "a");
  assert.match(text, /Where it comes from/);
  assert.match(text, /The full skill file is maintained at its external source/);
  assert.ok(anchors.some((anchor) => anchor.textContent === "Read the skill at its source"));
  assert.match(text, /gh skill install octo-org\/hub microsoft-foundry/);
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
