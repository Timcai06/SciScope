#!/usr/bin/env node

const path = require("node:path");
const { execFileSync } = require("node:child_process");

const packageRoot = path.resolve(__dirname, "..");

execFileSync(process.execPath, [path.join(packageRoot, "scripts", "install.js")], {
  cwd: packageRoot,
  stdio: "inherit",
  env: { ...process.env, SCISCOPE_TUI_SKIP_DOWNLOAD: "1" },
});

execFileSync(process.execPath, [path.join(packageRoot, "bin", "sciscope-tui.js"), "--version"], {
  cwd: packageRoot,
  stdio: "inherit",
});
