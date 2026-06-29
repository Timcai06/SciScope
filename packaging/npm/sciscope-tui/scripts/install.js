#!/usr/bin/env node

const fs = require("node:fs");
const https = require("node:https");
const os = require("node:os");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const packageRoot = path.resolve(__dirname, "..");
const pkg = require(path.join(packageRoot, "package.json"));

const supported = {
  darwin: { x64: "amd64", arm64: "arm64" },
  linux: { x64: "amd64", arm64: "arm64" },
  win32: { x64: "amd64", arm64: "arm64" },
};

function fail(message) {
  console.error(`sciscope-tui install: ${message}`);
  process.exit(1);
}

function platformTarget() {
  const platform = process.platform;
  const arch = process.arch;
  const archMap = supported[platform];
  if (!archMap || !archMap[arch]) {
    fail(`unsupported platform ${platform}/${arch}`);
  }
  return {
    os: platform === "win32" ? "windows" : platform,
    arch: archMap[arch],
    ext: platform === "win32" ? "zip" : "tar.gz",
  };
}

function download(url, destination, redirects = 0) {
  if (redirects > 5) {
    fail(`too many redirects while downloading ${url}`);
  }

  return new Promise((resolve, reject) => {
    const request = https.get(
      url,
      { headers: { "User-Agent": `sciscope-tui-npm/${pkg.version}` } },
      (response) => {
        const status = response.statusCode || 0;
        if ([301, 302, 303, 307, 308].includes(status) && response.headers.location) {
          response.resume();
          const next = new URL(response.headers.location, url).toString();
          download(next, destination, redirects + 1).then(resolve, reject);
          return;
        }

        if (status < 200 || status >= 300) {
          response.resume();
          reject(new Error(`HTTP ${status} for ${url}`));
          return;
        }

        const file = fs.createWriteStream(destination);
        response.pipe(file);
        file.on("finish", () => file.close(resolve));
        file.on("error", reject);
      }
    );
    request.on("error", reject);
  });
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function downloadWithRetry(url, destination, attempts = 4) {
  let lastError;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      fs.rmSync(destination, { force: true });
      await download(url, destination);
      return;
    } catch (error) {
      lastError = error;
      if (attempt === attempts) break;
      const delayMs = attempt * 1500;
      console.warn(
        `sciscope-tui install: download failed (${error.message}); retrying in ${delayMs}ms`
      );
      await wait(delayMs);
    }
  }
  throw lastError;
}

function extract(archivePath, destination, ext) {
  fs.mkdirSync(destination, { recursive: true });
  if (ext === "zip") {
    if (process.platform === "win32") {
      execFileSync(
        "powershell.exe",
        [
          "-NoProfile",
          "-ExecutionPolicy",
          "Bypass",
          "-Command",
          "Expand-Archive -LiteralPath $args[0] -DestinationPath $args[1] -Force",
          archivePath,
          destination,
        ],
        { stdio: "inherit" }
      );
      return;
    }
    execFileSync("unzip", ["-q", archivePath, "-d", destination], { stdio: "inherit" });
    return;
  }

  execFileSync("tar", ["-xzf", archivePath, "-C", destination], { stdio: "inherit" });
}

function findBinary(dir) {
  const wanted = process.platform === "win32" ? "sciscope-tui.exe" : "sciscope-tui";
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const current = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      const nested = findBinary(current);
      if (nested) return nested;
    } else if (entry.isFile() && entry.name === wanted) {
      return current;
    }
  }
  return null;
}

async function main() {
  const vendorDir = path.join(packageRoot, "vendor");
  fs.mkdirSync(vendorDir, { recursive: true });

  const binaryName = process.platform === "win32" ? "sciscope-tui.exe" : "sciscope-tui";
  const targetBinary = path.join(vendorDir, binaryName);

  if (process.env.SCISCOPE_TUI_SKIP_DOWNLOAD === "1") {
    fs.writeFileSync(
      targetBinary,
      process.platform === "win32"
        ? "@echo off\r\necho sciscope-tui test shim\r\n"
        : "#!/bin/sh\necho sciscope-tui test shim\n",
      "utf8"
    );
    fs.chmodSync(targetBinary, 0o755);
    console.log("sciscope-tui install: created test shim");
    return;
  }

  const target = platformTarget();
  const version = process.env.SCISCOPE_TUI_VERSION || pkg.version;
  const tag = version.startsWith("v") ? version : `v${version}`;
  const asset = `sciscope-tui_${target.os}_${target.arch}.${target.ext}`;
  const base =
    process.env.SCISCOPE_TUI_RELEASE_BASE ||
    `https://github.com/Timcai06/SciScope/releases/download/${tag}`;
  const url = `${base.replace(/\/$/, "")}/${asset}`;

  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "sciscope-tui-npm-"));
  const archivePath = path.join(tempDir, asset);
  const extractDir = path.join(tempDir, "extract");

  try {
    console.log(`sciscope-tui install: downloading ${url}`);
    await downloadWithRetry(url, archivePath);
    extract(archivePath, extractDir, target.ext);
    const extractedBinary = findBinary(extractDir);
    if (!extractedBinary) {
      fail(`release archive did not contain ${binaryName}`);
    }
    fs.copyFileSync(extractedBinary, targetBinary);
    fs.chmodSync(targetBinary, 0o755);
    console.log(`sciscope-tui install: installed ${target.os}/${target.arch}`);
  } catch (error) {
    fail(error.message);
  } finally {
    fs.rmSync(tempDir, { recursive: true, force: true });
  }
}

main();
