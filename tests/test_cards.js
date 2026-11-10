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
    this.listeners = {};
    const classes = new Set();
    this.classList = {
      add: (name) => classes.add(name),
      remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
      toggle: (name, active) => active ? classes.add(name) : classes.delete(name),
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
    this.textContent = "";
  }

  addEventListener(event, listener) {
    this.listeners[event] = listener;
  }
}

function descendants(node) {
  return node.children.flatMap((child) => [child, ...descendants(child)]);
}

function loadApp(pathname = "/", search = "") {
  const elements = {};
  for (const selector of [
    "#catalog", "#skill-detail", ".hero", ".hero-actions", ".signal-panel", ".skip-link",
    "#return-to-catalog", "#detail-content", "#hub-title", "#hub-tagline", "#hub-eyebrow",
    "#build-badge", "#hub-notice", "#skills-grid", "#tag-cloud", "#search", "#result-count",
    "#empty-state", "#copy-status", "meta[name=description]",
  ]) elements[selector] = new Element("div");
  elements["#skill-detail"].hidden = true;
  const filters = ["all", "local", "external"].map((kind) => {
    const button = new Element("button");
    button.dataset.kind = kind;
    return button;
  });
  const location = { pathname, search, hash: "" };
  const context = vm.createContext({
    URLSearchParams,
    location,
    history: {
      replaceState(_state, _unused, url) {
        const parsed = new URL(url, "https://example.test");
        Object.assign(location, { pathname: parsed.pathname, search: parsed.search, hash: parsed.hash });
      },
    },
    navigator: { clipboard: { writeText: async () => {} } },
    setTimeout: () => 1,
    clearTimeout: () => {},
    document: {
      createElement: (tag) => new Element(tag),
      querySelector: (selector) => elements[selector] || null,
      querySelectorAll: (selector) => {
        if (selector === ".filter") return filters;
        return Object.values(elements).flatMap(descendants)
          .filter((node) => (node.className || "").split(" ").includes(selector.slice(1)));
      },
      documentElement: new Element("html"),
      addEventListener: () => {},
    },
    // Keep bootstrap pending; these tests call the render helpers directly.
    fetch: () => new Promise(() => {}),
  });
  vm.runInContext(source, context);
  return { context, elements, filters };
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

function renderPage(app, skills) {
  app.context.skills = skills;
  vm.runInContext(
    "state.config = { title: 'Demo hub', repo: 'o/r', notice: 'Demo content, not an official system.' };" +
    "state.build = { env: 'preview', label: 'Preview · PR #9', pr: 9, sha: 'abcdef1234' };" +
    "state.skills = skills; renderAll(); wireStaticEvents();",
    app.context,
  );
}

test("every catalog title uses its stable ID, independent of title and kind", () => {
  const app = loadApp();
  const local = { ...foundry, title: "Renamed title" };
  const external = { ...foundry, name: "external-skill", kind: "external" };
  renderPage(app, [local, external]);
  const links = app.context.document.querySelectorAll(".skill-title-link");
  assert.deepEqual(links.map((link) => link.attributes.href), ["/skills/microsoft-foundry", "/skills/external-skill"]);
  assert.equal(links[0].textContent, "Renamed title");
});

test("direct local and external routes show curated guidance, canonical source and unchanged install controls", () => {
  for (const kind of ["local", "external"]) {
    const app = loadApp("/skills/microsoft-foundry");
    const skill = {
      ...foundry, kind,
      details: {
        whatItDoes: "Evaluate a demo agent.", whenToUse: "For an evaluation task.",
        whenNotToUse: "Not for unrelated deployments.", exampleTask: "Evaluate a sample agent.",
        author: "Known author", publisher: "Known publisher", guidanceOrigin: "demo",
        canonicalSource: "https://github.com/o/r/blob/main/skills/microsoft-foundry/SKILL.md",
      },
    };
    renderPage(app, [skill]);
    assert.equal(app.elements["#catalog"].hidden, true);
    assert.equal(app.elements["#skill-detail"].hidden, false);
    assert.equal(app.elements["#hub-title"].textContent, skill.title);
    assert.equal(app.context.document.title, `${skill.title} · Demo hub`);
    const content = app.elements["#detail-content"];
    const text = textOf(content);
    for (const value of [
      "What it does", "When to use it", "When not to use it", "Example task",
      "Demo-authored guidance", "Known author", "Known publisher", "not verification of safety",
      skill.details.whatItDoes, skill.details.whenToUse, skill.details.whenNotToUse, skill.details.exampleTask,
    ]) assert.ok(text.includes(value), value);
    const nodes = descendants(content);
    const sections = nodes.filter((node) => node.tag === "section");
    assert.deepEqual(sections.map((section) => section.children[0].textContent), [
      "What it does", "When to use it", "When not to use it", "Example task",
      "Source and attribution", "Install command",
    ]);
    const headingIds = sections.map((section) => section.children[0].attributes.id);
    assert.equal(new Set(headingIds).size, sections.length);
    for (const section of sections) {
      assert.equal(section.attributes["aria-labelledby"], section.children[0].attributes.id);
    }
    assert.equal(nodes.find((node) => node.tag === "a").attributes.href, skill.details.canonicalSource);
    assert.equal(nodes.find((node) => node.tag === "code").textContent, skill.installCommand);
    const copy = nodes.find((node) => node.tag === "button");
    assert.equal(copy.dataset.command, skill.installCommand);
    assert.equal(copy.attributes["aria-label"], `Copy install command for ${skill.title}`);
    assert.equal(app.elements["#build-badge"].textContent, "Preview · PR #9");
    assert.match(app.elements["#hub-notice"].textContent, /Demo content/);
    assert.equal(app.elements[".skip-link"].attributes.href, "#skill-detail");
  }
});

test("incomplete detail pages explicitly label missing guidance, attribution and canonical source", () => {
  const app = loadApp("/skills/microsoft-foundry/");
  renderPage(app, [{ ...foundry, details: { whatItDoes: "<script>literal text</script>", guidanceOrigin: "demo" } }]);
  const text = textOf(app.elements["#detail-content"]);
  for (const notice of [
    "Usage guidance is unavailable", "Limitations guidance is unavailable", "example task is unavailable",
    "Author attribution is unavailable", "Publisher attribution is unavailable",
    "canonical instruction source has not been identified", "<script>literal text</script>",
  ]) assert.ok(text.includes(notice), notice);
  const nodes = descendants(app.elements["#detail-content"]);
  assert.equal(nodes.find((node) => node.tag === "a").attributes.href, foundry.url);
  assert.equal(nodes.some((node) => node.tag === "script"), false);
  app.context.skill = { ...foundry };
  vm.runInContext("renderDetail(skill)", app.context);
  assert.match(textOf(app.elements["#detail-content"]), /Purpose guidance is unavailable/);
});

test("search, kind and tag survive title navigation, return links, and catalog reload", () => {
  const query = "?q=foundry+%26+demo&kind=local&tag=azure";
  const app = loadApp("/", query);
  const skill = { ...foundry, description: "foundry & demo" };
  renderPage(app, [skill]);
  assert.equal(app.elements["#search"].value, "foundry & demo");
  assert.equal(app.filters[1].attributes["aria-pressed"], "true");
  assert.equal(app.context.document.querySelectorAll(".tag-filter")[0].attributes["aria-pressed"], "true");
  assert.equal(app.elements["#result-count"].textContent, "1 skill");
  assert.equal(app.context.document.querySelectorAll(".skill-title-link")[0].attributes.href, `/skills/microsoft-foundry${query}`);
  app.elements["#search"].listeners.input({ target: { value: "sample / task" } });
  const updatedQuery = "?q=sample+%2F+task&kind=local&tag=azure";
  assert.equal(app.context.location.search, updatedQuery);
  assert.equal(app.context.document.querySelectorAll(".skill-title-link")[0].attributes.href, `/skills/microsoft-foundry${updatedQuery}`);
  const detail = loadApp("/skills/microsoft-foundry", updatedQuery);
  renderPage(detail, [skill]);
  assert.equal(detail.elements["#return-to-catalog"].attributes.href, `/${updatedQuery}#catalog`);
  const returned = loadApp("/", updatedQuery);
  renderPage(returned, [skill]);
  assert.equal(returned.elements["#search"].value, "sample / task");
  assert.equal(returned.elements["#result-count"].textContent, "0 skills");
});

test("unknown routes and loading failures retain the return link, badge and demo notice", () => {
  for (const path of ["/skills/missing", "/skills/Bad-ID", "/skills/name/extra"]) {
    const app = loadApp(path, "?kind=external");
    renderPage(app, [foundry]);
    assert.equal(app.elements["#hub-title"].textContent, "Skill not found");
    assert.equal(app.elements["#detail-content"].children.length, 0);
    assert.equal(app.elements["#return-to-catalog"].attributes.href, "/?kind=external#catalog");
    assert.match(app.elements["#hub-notice"].textContent, /Demo content/);
    assert.match(app.elements["#build-badge"].textContent, /Preview/);
    vm.runInContext("renderError(new Error('HTTP 503'))", app.context);
    assert.match(app.elements["#detail-content"].textContent, /HTTP 503/);
    assert.equal(app.elements["#skill-detail"].hidden, false);
  }
});

test("copy controls write the exact command and announce success, denial or unavailable clipboard", async () => {
  for (const outcome of ["success", "denied", "unavailable"]) {
    const app = loadApp("/skills/microsoft-foundry");
    renderPage(app, [foundry]);
    let written;
    if (outcome === "unavailable") app.context.navigator = {};
    else app.context.navigator.clipboard.writeText = async (command) => {
      written = command;
      if (outcome === "denied") throw new Error("Denied");
    };
    const button = descendants(app.elements["#detail-content"]).find((node) => node.tag === "button");
    await button.listeners.click();
    assert.equal(written, outcome === "unavailable" ? undefined : foundry.installCommand);
    assert.equal(button.textContent, outcome === "success" ? "Copied" : "Copy failed");
    assert.match(app.elements["#copy-status"].textContent,
      outcome === "success" ? /copied to clipboard/ : /Couldn't copy.*manually/);
    assert.ok(app.elements["#copy-status"].textContent.includes(foundry.title));
  }
});

test("bootstrap renders a directly opened route and cold load errors preserve query filters", async () => {
  const app = loadApp("/skills/microsoft-foundry", "?q=demo&kind=local&tag=azure");
  app.context.fetch = async (url) => {
    assert.equal(url, "/hub.json");
    return {
      ok: true,
      json: async () => ({
        config: { title: "Demo hub", repo: "o/r", notice: "Demo content." },
        skills: [foundry],
      }),
    };
  };
  await vm.runInContext("bootstrap()", app.context);
  assert.equal(app.elements["#hub-title"].textContent, foundry.title);
  assert.equal(app.elements["#return-to-catalog"].attributes.href, "/?q=demo&kind=local&tag=azure#catalog");
  const failed = loadApp("/skills/microsoft-foundry", "?q=demo&kind=local&tag=azure");
  failed.context.fetch = async () => ({ ok: false, status: 503 });
  await vm.runInContext("bootstrap()", failed.context);
  assert.match(failed.elements["#detail-content"].textContent, /HTTP 503/);
  assert.equal(failed.elements["#return-to-catalog"].attributes.href, "/?q=demo&kind=local&tag=azure#catalog");
});
