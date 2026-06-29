#!/usr/bin/env node

const fs = require("node:fs");
const path = require("node:path");
const { spawn } = require("node:child_process");

const packageRoot = path.resolve(__dirname, "..");
const binaryName = process.platform === "win32" ? "sciscope-tui.exe" : "sciscope-tui";
const binaryPath = path.join(packageRoot, "vendor", binaryName);

if (!fs.existsSync(binaryPath)) {
  console.error(
    [
      "SciScope TUI binary is missing.",
      "Try reinstalling with: npm install -g sciscope-tui",
      "If you are packaging locally, run: node scripts/install.js",
    ].join("\n")
  );
  process.exit(1);
}

const child = spawn(binaryPath, process.argv.slice(2), {
  stdio: "inherit",
  windowsHide: false,
});

child.on("error", (error) => {
  console.error(`Failed to start SciScope TUI: ${error.message}`);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
