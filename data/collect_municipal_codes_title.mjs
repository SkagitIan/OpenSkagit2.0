import fs from "node:fs/promises";
import path from "node:path";

const PRESETS = {
  anacortes_title19: {
    jurisdictionKey: "anacortes",
    titleName: "Title 19 Unified Development Code",
    titleUrl: "https://anacortes.municipal.codes/AMC/19",
    chapterPrefix: "19",
  },
};

function argValue(name, fallback = null) {
  const prefix = `${name}=`;
  const found = process.argv.find((arg) => arg.startsWith(prefix));
  return found ? found.slice(prefix.length) : fallback;
}

function hasFlag(name) {
  return process.argv.includes(name);
}

function stripHtml(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|tr|table|h[1-6]|li|section)>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\r/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function safeRef(url) {
  const parsed = new URL(url);
  const leaf = parsed.pathname.split("/").filter(Boolean).pop() || "page";
  return `${leaf.replace(/[^A-Za-z0-9_.-]+/g, "_")}.html`;
}

async function main() {
  if (hasFlag("--list-presets")) {
    console.log(JSON.stringify(PRESETS, null, 2));
    return;
  }
  const presetName = argValue("--preset", "anacortes_title19");
  const preset = PRESETS[presetName];
  if (!preset) throw new Error(`Unknown --preset=${presetName}.`);
  const outDir = argValue("--out", `output/municipal_codes/${presetName}`);
  const limit = Number(argValue("--limit", "0"));
  const headed = hasFlag("--headed");
  const freshPages = hasFlag("--fresh-pages");
  const resume = hasFlag("--resume");

  const { chromium } = await import("playwright");
  const browser = await chromium.launch({ headless: !headed });
  const page = await newMunicipalPage(browser);

  await gotoMunicipalContent(page, preset.titleUrl, preset.chapterPrefix);
  await page.waitForTimeout(500);
  const titleHtml = await page.content();
  const titleText = await page.locator("body").innerText().catch(() => "");
  assertUsableContent(titleText, preset.titleUrl);
  const links = await page.locator("a").evaluateAll((anchors, prefix) => {
    const pattern = new RegExp(`/AMC/${prefix}\\.\\d+$`);
    return [...anchors]
      .map((anchor) => {
        try {
          const href = new URL(anchor.getAttribute("href") || "", location.href).href;
          return { href, label: anchor.textContent.trim().replace(/\s+/g, " ") };
        } catch {
          return null;
        }
      })
      .filter((item) => item && pattern.test(new URL(item.href).pathname));
  }, preset.chapterPrefix);
  const uniqueLinks = [...new Map(links.map((item) => [item.href, item])).values()].sort((a, b) => a.href.localeCompare(b.href));
  const selected = limit > 0 ? uniqueLinks.slice(0, limit) : uniqueLinks;

  await fs.mkdir(path.join(outDir, "html"), { recursive: true });
  await fs.mkdir(path.join(outDir, "text"), { recursive: true });
  await fs.writeFile(path.join(outDir, "toc.html"), titleHtml, "utf8");
  await fs.writeFile(path.join(outDir, "toc.json"), JSON.stringify({ page_count: uniqueLinks.length, pages: uniqueLinks }, null, 2), "utf8");

  const records = [];
  for (const item of selected) {
    const ref = safeRef(item.href);
    const htmlPath = path.join(outDir, "html", ref);
    const textPath = path.join(outDir, "text", ref.replace(/\.html$/, ".txt"));
    if (resume && (await fileExists(htmlPath)) && (await fileExists(textPath))) {
      const text = await fs.readFile(textPath, "utf8");
      if (isUsableContent(text)) {
        records.push({
          ref,
          url: item.href,
          status: 200,
          mode: "browser-resume",
          chapter: item.label,
          text_length: text.length,
        });
        console.log(`resume 200 ${ref} ${text.length} chars`);
        continue;
      }
      console.log(`resume stale ${ref} ${text.length} chars; recollecting`);
    }
    const { html, text } = freshPages
      ? await collectFreshChapter(chromium, headed, item.href, item.href.split("/").pop())
      : await collectChapter(page, item.href, item.href.split("/").pop());
    assertUsableContent(text, item.href);
    await fs.writeFile(htmlPath, html, "utf8");
    await fs.writeFile(textPath, text, "utf8");
    records.push({
      ref,
      url: item.href,
      status: 200,
      mode: "browser",
      chapter: item.label,
      text_length: text.length,
    });
    console.log(`browser 200 ${ref} ${text.length} chars`);
    if (!freshPages) {
      await page.waitForTimeout(2500);
    }
  }

  await browser.close();

  const corpus = {
    jurisdiction: preset.jurisdictionKey,
    jurisdiction_key: preset.jurisdictionKey,
    title: preset.titleName,
    source: preset.titleUrl,
    preset: presetName,
    platform: "municipal.codes",
    collected_at: new Date().toISOString(),
    page_count: records.length,
    toc_page_count: uniqueLinks.length,
    pages: records,
  };
  await fs.writeFile(path.join(outDir, "corpus.json"), JSON.stringify(corpus, null, 2), "utf8");
  console.log(`Wrote ${records.length} page records to ${path.resolve(outDir)}`);
}

async function newFreshPage(chromium, headed) {
  const browser = await chromium.launch({ headless: !headed });
  return newMunicipalPage(browser);
}

async function newMunicipalPage(browser) {
  return browser.newPage({
    userAgent: "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
  });
}

async function collectFreshChapter(chromium, headed, url, marker) {
  let lastError = null;
  for (let attempt = 1; attempt <= 4; attempt++) {
    let browser = null;
    try {
      browser = await chromium.launch({ headless: !headed });
      const page = await newMunicipalPage(browser);
      const result = await collectChapter(page, url, marker);
      await browser.close();
      return result;
    } catch (error) {
      lastError = error;
      if (browser) {
        await browser.close().catch(() => {});
      }
      await new Promise((resolve) => setTimeout(resolve, 5000 * attempt));
    }
  }
  throw lastError;
}

async function collectChapter(page, url, marker) {
  await gotoMunicipalContent(page, url, marker);
  const html = await page.content();
  const text = stripHtml(html);
  return { html, text };
}

async function gotoMunicipalContent(page, url, marker) {
  for (let attempt = 1; attempt <= 4; attempt++) {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
    await waitForMunicipalContent(page, marker);
    const text = await page.locator("body").innerText().catch(() => "");
    if (!isChallenge(text) && text.includes(marker) && text.length >= 300) {
      return;
    }
    await page.waitForTimeout(8000 * attempt);
  }
}

async function waitForMunicipalContent(page, marker) {
  await page
    .waitForFunction(
      (expected) => {
        const text = document.body?.innerText || "";
        return (!/Just a moment|security verification|Enable JavaScript and cookies/i.test(text) && text.includes(expected) && text.length > 300)
          || text.length > 1000;
      },
      marker,
      { timeout: 90000 }
    )
    .catch(async () => {
      await page.waitForTimeout(5000);
    });
}

function assertUsableContent(text, url) {
  if (!isUsableContent(text)) {
    throw new Error(`Municipal Code content was not available for ${url}; got ${text.length} chars.`);
  }
}

function isUsableContent(text) {
  return !isChallenge(text) && text.length >= 300;
}

function isChallenge(text) {
  return /Just a moment|security verification|Enable JavaScript and cookies|Verification successful/i.test(text);
}

async function fileExists(filePath) {
  return fs.access(filePath).then(() => true).catch(() => false);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
