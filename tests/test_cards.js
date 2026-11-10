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
    this.events = {};
    this.classList = {
      toggle: (name, active) => {
        const classes = new Set((this.className || "").split(" ").filter(Boolean));
        if (active) classes.add(name);
        else classes.delete(name);
        this.className = [...classes].join(" ");
      },
      add: (name) => this.classList.toggle(name, true),
      remove: (name) => this.classList.toggle(name, false),
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

  addEventListener(name, callback) {
    this.events[name] = callback;
  }
}

function loadApp(url = "https://hub.example/") {
  const elements = {};
  const window = {
    location: new URL(url),
    history: {
      replaceState(_state, _unused, href) {
        window.location = new URL(href, window.location);
      },
    },
  };
  const context = vm.createContext({
    window,
    URL,
    URLSearchParams,
    setTimeout: () => {},
    document: {
      createElement: (tag) => new Element(tag),
      querySelector: (selector) => elements[selector] || null,
      querySelectorAll: (selector) => {
        if (selector === ".skill-card") return elements["#skills-grid"]?.children || [];
        if (selector === ".tag-filter") return elements["#tag-cloud"]?.children || [];
        return elements[selector] || [];
      },
      addEventListener() {},
      documentElement: new Element("html"),
    },
    // Keep bootstrap pending; these tests call the render helpers directly.
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(source, context);
  return { context, elements };
}

function loadPage(url) {
  const app = loadApp(url);
  for (const selector of [
    "#catalog", "#skill-detail", "#hub-title", "#hub-tagline", "#hub-eyebrow",
    "#hub-cta", "#hub-install-cmd", "#repo-link", "#build-badge", "#hub-notice",
    "#signal-total", "#signal-local", "#signal-external", "#signal-owner",
    "#search", "#tag-cloud", "#skills-grid", "#result-count", "#empty-state",
    ".hero-actions", ".signal-panel", ".hero", ".skip-link", "meta[name=description]",
  ]) app.elements[selector] = new Element("div");
  app.elements[".filter"] = ["all", "local", "external"].map((kind) => {
    const button = new Element("button");
    button.dataset.kind = kind;
    return button;
  });
  return app;
}

function descendants(node) {
  return [node, ...node.children.flatMap(descendants)];
}

function textOf(node) {
  return [node.textContent, ...node.children.map(textOf)].join(" ");
}

const foundry = {
  name: "microsoft-foundry",
  title: "Microsoft Foundry",
  description: "Deploy and evaluate agents.",
  whenToUse: "When deploying or evaluating a Foundry agent.",
  skillFile: "---\nname: microsoft-foundry\n---\n# Instructions\n<script>alert('literal')</script>\n",
  tags: ["azure"],
  kind: "local",
  agentSkill: false,
  license: "MIT",
  source: "Microsoft",
  url: "https://github.com/octo-org/hub/tree/main/skills/microsoft-foundry",
  installCommand: "gh skill install octo-org/hub microsoft-foundry",
  footprint: { indexTokens: 180, bodyTokens: 1234, files: 87, fileTokens: 182345 },
};

function pageData() {
  return {
    config: { title: "Test hub", repo: "octo-org/hub", notice: "Demo content only." },
    build: { env: "preview", sha: "abcdef1234", pr: 3, label: "Preview build" },
    skills: [
      foundry,
      { ...foundry, name: "git-commit", title: "Git Commit", kind: "external",
        source: "github/awesome-copilot", license: "See source",
        footprint: undefined, skillFile: undefined, url: "https://skills.sh/github/awesome-copilot/git-commit" },
    ],
  };
}

async function bootstrapPage(app) {
  const requests = [];
  app.context.fetch = async (url) => {
    requests.push(url);
    return { ok: true, json: async () => pageData() };
  };
  await vm.runInContext("bootstrap()", app.context);
  assert.deepEqual(requests, ["/hub.json"]);
}

test("direct local detail routes show the full literal file, provenance and working install copy", async () => {
  const app = loadPage("https://hub.example/skills/microsoft-foundry");
  let copied;
  app.context.navigator = { clipboard: { writeText: async (text) => { copied = text; } } };
  await bootstrapPage(app);
  const detail = app.elements["#skill-detail"];
  assert.equal(app.elements["#catalog"].hidden, true);
  assert.equal(detail.hidden, false);
  assert.equal(app.elements["#hub-title"].textContent, "Microsoft Foundry");
  assert.equal(app.context.document.title, "Microsoft Foundry | Test hub");
  assert.equal(app.elements[".skip-link"].attributes.href, "#skill-detail");
  assert.equal(app.elements["#build-badge"].textContent, "Preview build");
  assert.equal(app.elements["#hub-notice"].textContent, "Demo content only.");
  assert.match(textOf(detail), /What it does.*Deploy and evaluate agents/s);
  assert.match(textOf(detail), /When to use.*When deploying/s);
  assert.match(textOf(detail), /Credited source.*Microsoft.*Hub repository.*octo-org\/hub/s);
  assert.match(textOf(detail), /build-time copy, not a live upstream version/);
  assert.match(textOf(detail), /Context footprint/);
  const nodes = descendants(detail);
  const pre = nodes.find((node) => node.tag === "pre");
  assert.equal(pre.children[0].textContent, foundry.skillFile);
  assert.equal(pre.children[0].children.length, 0);
  const source = nodes.find((node) => node.tag === "a" && node.attributes.href === foundry.url);
  assert.equal(source.textContent, "View hub source and supporting files");
  const button = nodes.find((node) => node.tag === "button");
  await button.events.click();
  assert.equal(copied, foundry.installCommand);
  assert.equal(button.textContent, "Copied");
});

test("external detail routes link upstream without loading or rendering a full file", async () => {
  const app = loadPage("https://hub.example/skills/git-commit");
  await bootstrapPage(app);
  const detail = app.elements["#skill-detail"];
  const nodes = descendants(detail);
  assert.match(textOf(detail), /external.*Credited source.*github\/awesome-copilot.*See source/s);
  assert.match(textOf(detail), /full skill file is not hosted in this hub/);
  assert.doesNotMatch(textOf(detail), /Context footprint|Hub repository|build-time copy/);
  assert.equal(nodes.some((node) => node.tag === "pre"), false);
  const upstream = nodes.find((node) => node.textContent === "Read skill upstream");
  assert.equal(upstream.attributes.href, pageData().skills[1].url);
});

test("unknown and malformed routes show a recoverable not-found view with shared notices", async () => {
  for (const path of ["/skills/no-such-skill", "/skills", "/skills/microsoft-foundry/extra", "/skills/%E0%A4%A"]) {
    const app = loadPage(`https://hub.example${path}`);
    await bootstrapPage(app);
    assert.equal(app.elements["#hub-title"].textContent, "Skill not found");
    assert.equal(app.elements["#catalog"].hidden, true);
    assert.equal(app.elements["#skill-detail"].hidden, false);
    assert.equal(app.elements["#skill-detail"].children[0].attributes.href, "/");
    assert.equal(app.elements["#build-badge"].textContent, "Preview build");
    assert.equal(app.elements["#hub-notice"].textContent, "Demo content only.");
  }
});

test("catalog filter URLs restore state and controls when returning from a detail page", async () => {
  const app = loadPage("https://hub.example/?q=agents&kind=local&tag=azure");
  await bootstrapPage(app);
  assert.equal(app.elements["#skill-detail"].hidden, true);
  assert.equal(app.elements["#catalog"].hidden, false);
  assert.equal(app.elements["#search"].value, "agents");
  assert.equal(app.elements[".filter"][1].attributes["aria-pressed"], "true");
  const azure = app.elements["#tag-cloud"].children.find((node) => node.dataset.tag === "azure");
  assert.equal(azure.attributes["aria-pressed"], "true");
  assert.equal(app.elements["#result-count"].textContent, "1 skill");
  const card = app.elements["#skills-grid"].children[0];
  assert.equal(descendants(card).find((node) => node.textContent === foundry.title).attributes.href,
    "/skills/microsoft-foundry");
  app.elements["#search"].events.input({ target: { value: "Foundry" } });
  vm.runInContext("setKind('external'); toggleTag('azure');", app.context);
  const returnUrl = app.context.window.location.href;
  assert.equal(new URL(returnUrl).searchParams.get("q"), "Foundry");
  assert.equal(new URL(returnUrl).searchParams.get("kind"), "external");
  assert.equal(new URL(returnUrl).searchParams.has("tag"), false);
  const restored = loadPage(returnUrl);
  await bootstrapPage(restored);
  assert.equal(restored.elements["#search"].value, "Foundry");
  assert.equal(restored.elements[".filter"][2].attributes["aria-pressed"], "true");
  assert.equal(restored.elements["#result-count"].textContent, "0 skills");
});

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
