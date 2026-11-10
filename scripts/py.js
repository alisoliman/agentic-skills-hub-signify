#!/usr/bin/env node
// Runs a Python 3 script with whichever interpreter this machine has, so the npm scripts
// work the same on macOS, Linux and Windows: python3, python, or the Windows "py -3" launcher.
"use strict";

const { spawnSync } = require("node:child_process");

const MINIMUM = [3, 9];
const CANDIDATES =
  process.platform === "win32"
    ? [["py", ["-3"]], ["python", []], ["python3", []]]
    : [["python3", []], ["python", []]];

function pythonVersion(command, prefix) {
  const probe = spawnSync(command, [...prefix, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"], {
    encoding: "utf8",
  });
  if (probe.error || probe.status !== 0) return null;
  const [major, minor] = probe.stdout.trim().split(".").map(Number);
  return Number.isInteger(major) && Number.isInteger(minor) ? [major, minor] : null;
}

function isSupported([major, minor]) {
  return major > MINIMUM[0] || (major === MINIMUM[0] && minor >= MINIMUM[1]);
}

for (const [command, prefix] of CANDIDATES) {
  const version = pythonVersion(command, prefix);
  if (!version || !isSupported(version)) continue;
  const result = spawnSync(command, [...prefix, ...process.argv.slice(2)], { stdio: "inherit" });
  if (result.error) {
    console.error(result.error.message);
    process.exit(1);
  }
  process.exit(result.status === null ? 1 : result.status);
}

console.error(
  `Python ${MINIMUM.join(".")}+ was not found. Install it from https://www.python.org/downloads/ ` +
    "(macOS: brew install python, Windows: winget install Python.Python.3.12) and try again.",
);
process.exit(1);
