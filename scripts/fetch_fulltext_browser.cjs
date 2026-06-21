#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const url = process.argv[2];
if (!url) {
  console.error("usage: fetch_fulltext_browser.cjs <url>");
  process.exit(2);
}

const timeoutMs = Number(process.env.SCISCOPE_BROWSER_TIMEOUT_MS || "30000");
const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

function clean(text) {
  return String(text || "").replace(/\s+/g, " ").trim();
}

async function main() {
  const launchOptions = { headless: true };
  if (fs.existsSync(chromePath)) {
    launchOptions.executablePath = chromePath;
  }
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage({
      userAgent:
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      viewport: { width: 1280, height: 1800 },
      locale: "en-US",
    });
    page.setDefaultTimeout(timeoutMs);
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    await page.waitForLoadState("networkidle", { timeout: Math.min(timeoutMs, 10000) }).catch(() => {});

    const result = await page.evaluate(() => {
      const selectors = [
        "article",
        ".html-article-content",
        ".article-content",
        "#html-body",
        ".art-content",
        "main",
        "body",
      ];
      for (const selector of selectors) {
        const node = document.querySelector(selector);
        if (!node) continue;
        const clone = node.cloneNode(true);
        clone.querySelectorAll("script,style,nav,header,footer,aside,form,.references,.article-nav").forEach((el) => el.remove());
        const text = clone.innerText || clone.textContent || "";
        if (text.split(/\s+/).length >= 80) {
          return { selector, title: document.title || "", text };
        }
      }
      return { selector: "", title: document.title || "", text: document.body ? document.body.innerText : "" };
    });
    console.log(JSON.stringify({ ...result, text: clean(result.text), url }));
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
});
