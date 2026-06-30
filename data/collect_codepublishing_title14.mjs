import fs from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_HAR = "C:/Users/ian/Downloads/skagit-zoning-har.har";
const BASE = "https://www.codepublishing.com";
const PRESETS = {
  skagit_county_title14: {
    jurisdictionKey: "skagit_county",
    jurisdictionPath: "/WA/SkagitCounty/",
    titleId: "SkagitCounty14",
    titleName: "Title 14 Unified Development Code",
    defaultHar: DEFAULT_HAR,
  },
  mount_vernon_title17: {
    jurisdictionKey: "mount_vernon",
    jurisdictionPath: "/WA/MountVernon/",
    titleId: "MountVernon17",
    titleName: "Title 17 Zoning",
  },
  burlington_title17: {
    jurisdictionKey: "burlington",
    jurisdictionPath: "/WA/Burlington/",
    titleId: "Burlington17",
    titleName: "Title 17 Zoning",
  },
  sedro_woolley_title17: {
    jurisdictionKey: "sedro_woolley",
    jurisdictionPath: "/WA/SedroWoolley/",
    titleId: "SedroWoolley17",
    titleName: "Title 17 Zoning",
  },
  anacortes_title19: {
    jurisdictionKey: "anacortes",
    jurisdictionPath: "/WA/Anacortes/",
    titleId: "Anacortes19",
    titleName: "Title 19 Unified Development Code",
  },
  concrete_title19: {
    jurisdictionKey: "concrete",
    jurisdictionPath: "/WA/Concrete/",
    titleId: "Concrete19",
    titleName: "Title 19 Development Regulations",
  },
  la_conner_title15: {
    jurisdictionKey: "la_conner",
    jurisdictionPath: "/WA/LaConner/",
    titleId: "LaConner15",
    titleName: "Title 15 Uniform Development Code",
  },
};
const OUT_DIR = "output/codepublishing/skagit_county_title14";

const browserHeaders = {
  "accept": "text/plain, */*; q=0.01",
  "x-requested-with": "XMLHttpRequest",
  "user-agent": "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
};

function argValue(name, fallback = null) {
  const prefix = `${name}=`;
  const found = process.argv.find((arg) => arg.startsWith(prefix));
  return found ? found.slice(prefix.length) : fallback;
}

function hasFlag(name) {
  return process.argv.includes(name);
}

function unique(values) {
  return [...new Set(values)];
}

function stripHtml(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|div|tr|table|h[1-6]|li)>/gi, "\n")
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

function titleFromHtml(html, fallback) {
  const h1 = html.match(/<h1[^>]*>([\s\S]*?)<\/h1>/i);
  if (h1) return stripHtml(h1[1]).replace(/\s+/g, " ").trim();
  const title = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  if (title) return stripHtml(title[1]).replace(/\s+/g, " ").trim();
  return fallback;
}

function sectionAnchors(html) {
  const anchors = [];
  const regex = /<a\b[^>]*\bname=["']([^"']+)["'][^>]*>|<[^>]+\bid=["']([^"']+)["'][^>]*>/gi;
  for (const match of html.matchAll(regex)) {
    const id = match[1] || match[2];
    if (/^14\.\d+(\.\d+)?/.test(id)) anchors.push(id);
  }
  return unique(anchors);
}

async function readHarDiscovery(harPath, titleId) {
  const raw = await fs.readFile(harPath, "utf8");
  const har = JSON.parse(raw);
  const entries = har.log?.entries || [];
  const readerEntry = entries.find((entry) => entry.request?.url?.includes(`reader.pl?cite=${titleId}`) && entry.response?.content?.text);
  if (!readerEntry) throw new Error(`No embedded ${titleId} reader.pl response found in HAR: ${harPath}`);
  const tocHtml = readerEntry.response.content.text;
  const escapedTitle = titleId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pageRefs = unique([...tocHtml.matchAll(new RegExp(`\\.\\./html/${escapedTitle}/(${escapedTitle}\\d+\\.html)`, "g"))].map((match) => match[1])).sort();
  const sections = [...tocHtml.matchAll(/<a\b[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g)]
    .map((match) => ({
      href: match[1],
      label: stripHtml(match[2]).replace(/\s+/g, " ").trim(),
    }))
    .filter((item) => item.href.includes(`/${titleId}/`));
  return { tocHtml, pageRefs, sections };
}

async function fetchDirect(url, referer) {
  const response = await fetch(url, { headers: { ...browserHeaders, referer } });
  const text = await response.text();
  if (!response.ok || /Just a moment|cf-browser-verification|challenge-platform/i.test(text)) {
    return { ok: false, status: response.status, text };
  }
  return { ok: true, status: response.status, text };
}

async function fetchWithBrowser(page, url) {
  const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(500);
  const html = await page.content();
  return { status: response?.status() || 0, text: html };
}

async function discoverWithBrowser(config, outDir) {
  const { chromium } = await loadPlaywright();
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    userAgent: browserHeaders["user-agent"],
    extraHTTPHeaders: {
      "accept-language": "en-US,en;q=0.9",
    },
  });
  const hashUrl = `${BASE}${config.jurisdictionPath}#!/${config.titleId}/${config.titleId}.html`;
  let tocHtml = "";
  try {
    await page.goto(hashUrl, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(5000);
    tocHtml = await page.locator("body").innerHTML();
  } catch {
    tocHtml = "";
  }
  if (!tocHtml || !tocHtml.includes(config.titleId)) {
    await page.goto(`${BASE}${config.jurisdictionPath}`, { waitUntil: "domcontentloaded", timeout: 90000 });
    const readerUrl = `${BASE}${config.jurisdictionPath}cgi/reader.pl?cite=${config.titleId}&check=false&boxen=true&archive=html&_=${Date.now()}`;
    await page.goto(readerUrl, { waitUntil: "domcontentloaded", timeout: 90000 });
    tocHtml = await page.locator("body").innerHTML();
  }
  await browser.close();
  if (/Just a moment|cf-browser-verification|challenge-platform/i.test(tocHtml)) {
    throw new Error(`Browser discovery was challenged for ${config.titleId}`);
  }
  const tmpHar = path.join(outDir, "_browser_discovery_toc.html");
  await fs.mkdir(outDir, { recursive: true });
  await fs.writeFile(tmpHar, tocHtml, "utf8");
  const escapedTitle = config.titleId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pageRefs = unique([
    ...[...tocHtml.matchAll(new RegExp(`\\.\\./html/${escapedTitle}/(${escapedTitle}\\d+\\.html)`, "g"))].map((match) => match[1]),
    ...[...tocHtml.matchAll(new RegExp(`${escapedTitle}/(${escapedTitle}\\d+\\.html)`, "g"))].map((match) => match[1]),
  ]).sort();
  const sections = [...tocHtml.matchAll(/<a\b[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/g)]
    .map((match) => ({ href: match[1], label: stripHtml(match[2]).replace(/\s+/g, " ").trim() }))
    .filter((item) => item.href.includes(`/${config.titleId}/`));
  return { tocHtml, pageRefs, sections };
}

async function loadPlaywright() {
  try {
    return await import("playwright");
  } catch (error) {
    const require = createRequire(import.meta.url);
    const nodePath = process.env.NODE_PATH || "";
    for (const root of nodePath.split(path.delimiter).filter(Boolean)) {
      try {
        return require(path.join(root, "playwright"));
      } catch {
        // Try the next NODE_PATH entry.
      }
    }
    throw error;
  }
}

async function main() {
  const presetName = argValue("--preset", "skagit_county_title14");
  const preset = PRESETS[presetName];
  if (hasFlag("--list-presets")) {
    console.log(JSON.stringify(PRESETS, null, 2));
    return;
  }
  if (!preset) throw new Error(`Unknown --preset=${presetName}. Use --list-presets.`);
  const config = {
    ...preset,
    jurisdictionKey: argValue("--jurisdiction-key", preset.jurisdictionKey),
    jurisdictionPath: argValue("--jurisdiction-path", preset.jurisdictionPath),
    titleId: argValue("--title-id", preset.titleId),
    titleName: argValue("--title-name", preset.titleName),
  };
  const harPath = argValue("--har", preset.defaultHar || "");
  const outDir = argValue("--out", OUT_DIR.replace("skagit_county_title14", presetName));
  const forceBrowser = hasFlag("--browser");
  const noBrowser = hasFlag("--no-browser");
  const limit = Number(argValue("--limit", "0"));

  let discovery;
  if (harPath && await fs.stat(harPath).then(() => true).catch(() => false)) {
    discovery = await readHarDiscovery(harPath, config.titleId);
  } else {
    discovery = await discoverWithBrowser(config, outDir);
  }
  const { tocHtml, pageRefs, sections } = discovery;
  const selectedRefs = limit > 0 ? pageRefs.slice(0, limit) : pageRefs;
  await fs.mkdir(path.join(outDir, "html"), { recursive: true });
  await fs.mkdir(path.join(outDir, "text"), { recursive: true });
  await fs.writeFile(path.join(outDir, "toc.html"), tocHtml, "utf8");
  await fs.writeFile(path.join(outDir, "toc.json"), JSON.stringify({ page_count: pageRefs.length, section_count: sections.length, pages: pageRefs, sections }, null, 2), "utf8");

  let browser = null;
  let page = null;
  const records = [];

  for (const ref of selectedRefs) {
    const pageUrl = `${BASE}${config.jurisdictionPath}html/${config.titleId}/${ref}`;
    const apiUrl = `${pageUrl}?_=${Date.now()}`;
    let mode = "direct";
    let result = forceBrowser ? { ok: false, status: 0, text: "" } : await fetchDirect(apiUrl, `${BASE}${config.jurisdictionPath}`);

    if (!result.ok) {
      if (noBrowser) {
        records.push({ ref, url: pageUrl, status: result.status, mode: "direct_failed", error: "Direct request blocked or failed; browser fallback disabled." });
        continue;
      }
      if (!browser) {
        const { chromium } = await loadPlaywright();
        browser = await chromium.launch({ headless: true });
        page = await browser.newPage({
          userAgent: browserHeaders["user-agent"],
          extraHTTPHeaders: {
            "accept-language": "en-US,en;q=0.9",
          },
        });
      }
      mode = "browser";
      result = await fetchWithBrowser(page, pageUrl);
    }

    const html = result.text;
    const text = stripHtml(html);
    const chapter = titleFromHtml(html, ref);
    const anchors = sectionAnchors(html);
    await fs.writeFile(path.join(outDir, "html", ref), html, "utf8");
    await fs.writeFile(path.join(outDir, "text", ref.replace(/\.html$/, ".txt")), text, "utf8");
    records.push({
      ref,
      url: pageUrl,
      status: result.status,
      mode,
      chapter,
      text_length: text.length,
      section_anchors: anchors,
    });
    console.log(`${mode} ${result.status} ${ref} ${text.length} chars`);
  }

  if (browser) await browser.close();

  const corpus = {
    jurisdiction: config.jurisdictionKey,
    title: config.titleName,
    source: `${BASE}${config.jurisdictionPath}#!/${config.titleId}/${config.titleId}.html`,
    discovered_from_har: harPath || null,
    preset: presetName,
    jurisdiction_key: config.jurisdictionKey,
    title_id: config.titleId,
    collected_at: new Date().toISOString(),
    page_count: records.length,
    toc_page_count: pageRefs.length,
    toc_section_count: sections.length,
    pages: records,
  };
  await fs.writeFile(path.join(outDir, "corpus.json"), JSON.stringify(corpus, null, 2), "utf8");
  console.log(`Wrote ${records.length} page records to ${path.resolve(outDir)}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
