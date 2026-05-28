#!/usr/bin/env node
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { createWriteStream, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { spawn } from "node:child_process";
import { connect } from "node:net";
import { randomBytes, createHash } from "node:crypto";
import { EventEmitter } from "node:events";

const DEFAULT_KEYWORDS = [
  "M8 304 外六角螺栓",
  "3M 口罩 N95",
  "德力西 断路器 2P 32A",
  "SKF 轴承 6205",
  "世达 内六角扳手套装",
];

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const keywords = args.keywords.length ? args.keywords : DEFAULT_KEYWORDS;
  const limit = Number(args.limit || 10);
  const minResults = Number(args.minResults || 1);
  const timeoutMs = Number(args.timeoutMs || 30000);
  const port = Number(args.port || 9222);
  const chromePath = args.chromePath || findChromePath();
  const headless = args.headless !== "false";
  const reportPath = resolve(args.report || "extension/chrome/validation/jd-search-real-report.json");

  if (!chromePath) {
    throw new Error("未找到 Chrome。可用 --chrome-path 指定 Chrome/Chromium 可执行文件。");
  }

  const userDataDir = args.userDataDir
    ? resolve(args.userDataDir)
    : await mkdtemp(join(tmpdir(), "mro-jd-validation-"));
  const chrome = spawn(chromePath, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${userDataDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-extensions",
    ...(headless ? ["--headless=new", "--disable-gpu"] : []),
    "about:blank",
  ], { stdio: ["ignore", "ignore", "pipe"] });

  const stderrPath = join(userDataDir, "chrome-stderr.log");
  chrome.stderr.pipe(createWriteStream(stderrPath));

  try {
    await connectBrowser(port, timeoutMs);
    const parserSource = await buildParserSource(limit);
    const results = [];

    for (const keyword of keywords) {
      const url = buildSearchUrl(args.baseUrl, keyword);
      const page = await openPage(port, url, timeoutMs);
      await sleep(Number(args.settleMs || 2500));
      let diagnostics = await evaluate(page.webSocketDebuggerUrl, diagnosticsSource(), timeoutMs);
      if (diagnostics.loginRequired && Number(args.loginWaitMs || 0) > 0) {
        console.log(`LOGIN_REQUIRED ${keyword}: 请在打开的 Chrome 窗口完成京东登录...`);
        await sleep(Number(args.loginWaitMs));
        await navigate(page.webSocketDebuggerUrl, url, timeoutMs);
        await sleep(Number(args.settleMs || 2500));
        diagnostics = await evaluate(page.webSocketDebuggerUrl, diagnosticsSource(), timeoutMs);
      }
      const offers = await evaluate(page.webSocketDebuggerUrl, parserSource, timeoutMs);
      await closePage(port, page.id);
      results.push({
        keyword,
        url,
        diagnostics,
        count: offers.length,
        sample: offers.slice(0, 3).map((offer) => ({
          title: offer.title,
          priceText: offer.priceText || null,
          productUrl: offer.productUrl,
          platformSku: offer.platformSku || null,
        })),
      });
    }

    const passed = results.filter((item) => item.count >= minResults).length;
    const report = {
      checkedAt: new Date().toISOString(),
      chromePath,
      headless,
      limit,
      minResults,
      requiredKeywords: keywords.length,
      passedKeywords: passed,
      ok: passed === keywords.length,
      results,
    };
    await writeJson(reportPath, report);
    printReport(report, reportPath);
    if (!report.ok) process.exitCode = 1;
  } finally {
    await terminateChrome(chrome);
    if (!args.userDataDir) {
      await rm(userDataDir, { recursive: true, force: true });
    }
  }
}

function parseArgs(argv) {
  const parsed = { keywords: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--keyword") {
      parsed.keywords.push(argv[index + 1]);
      index += 1;
    } else if (arg.startsWith("--")) {
      const key = arg.slice(2).replace(/-([a-z])/g, (_, char) => char.toUpperCase());
      parsed[key] = argv[index + 1];
      index += 1;
    }
  }
  return parsed;
}

function findChromePath() {
  const candidates = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
  ];
  return candidates.find((candidate) => existsSync(candidate));
}

function buildSearchUrl(baseUrl, keyword) {
  const encoded = encodeURIComponent(keyword);
  if (baseUrl) return baseUrl.replace("{keyword}", encoded);
  return `https://search.jd.com/Search?keyword=${encoded}&enc=utf-8`;
}

async function buildParserSource(limit) {
  const parserPath = resolve("extension/chrome/src/jdParser.js");
  const source = await readFile(parserPath, "utf8");
  return `
    (() => {
      ${source.replace("export function parseJdSearchPage", "function parseJdSearchPage")}
      return parseJdSearchPage(${JSON.stringify(limit)});
    })()
  `;
}

function diagnosticsSource() {
  return `
    (() => ({
      title: document.title,
      currentUrl: location.href,
      isSearchResultPage: ((/(^|\\.)search\\.jd\\.com$/.test(location.hostname) && /\\/Search/.test(location.pathname)) || (/(^|\\.)i-search\\.jd\\.com$/.test(location.hostname) && /\\/search/.test(location.pathname))),
      bodyLength: document.body?.innerText?.length || 0,
      candidateCards: document.querySelectorAll("[class*='goods'], [class*='product'], [class*='item'], li").length,
      links: document.querySelectorAll("a[href]").length,
      jdItemLinks: Array.from(document.querySelectorAll("a[href]")).filter((node) => /item\\.jd\\.com|mro\\.jd\\.com\\/.*(?:item|product|sku)|\\/\\d+\\.html|chat\\.jd\\.com\\/index\\.action.*[?&]pid=/.test(node.href)).length,
      linkSamples: Array.from(document.querySelectorAll("a[href]"))
        .slice(0, 20)
        .map((node) => ({
          href: node.href,
          text: String(node.innerText || node.getAttribute("title") || "").replace(/\\s+/g, " ").trim().slice(0, 120)
        })),
      itemSamples: Array.from(document.querySelectorAll("a[href]"))
        .filter((node) => /item\\.jd\\.com|mro\\.jd\\.com\\/.*(?:item|product|sku)|\\/\\d+\\.html|chat\\.jd\\.com\\/index\\.action.*[?&]pid=/.test(node.href))
        .slice(0, 5)
        .map((node) => ({
          href: node.href,
          text: String(node.innerText || node.getAttribute("title") || "").replace(/\\s+/g, " ").trim().slice(0, 120),
          parentText: String(node.closest("li, [class*='goods'], [class*='product'], [class*='item']")?.innerText || "").replace(/\\s+/g, " ").trim().slice(0, 200)
        })),
      hasPriceText: /¥|￥/.test(document.body?.innerText || ""),
      hasLoginText: /登录|请登录/.test(document.body?.innerText || ""),
      hasCaptchaText: /验证码|安全验证|滑块/.test(document.body?.innerText || ""),
      loginRequired: /passport\\.jd\\.com|\\/login/.test(location.href) || (/登录|请登录/.test(document.body?.innerText || "") && !/¥|￥/.test(document.body?.innerText || ""))
    }))()
  `;
}

async function connectBrowser(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      return await fetchJson(`http://127.0.0.1:${port}/json/version`);
    } catch {
      await sleep(250);
    }
  }
  throw new Error(`Chrome DevTools 连接超时：127.0.0.1:${port}`);
}

async function openPage(port, url, timeoutMs) {
  const page = await fetchJson(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`);
  await waitForLoad(page.webSocketDebuggerUrl, timeoutMs);
  return page;
}

async function closePage(port, pageId) {
  await fetch(`http://127.0.0.1:${port}/json/close/${pageId}`).catch(() => {});
}

async function waitForLoad(wsUrl, timeoutMs) {
  await withSocket(wsUrl, timeoutMs, async (socket, send) => {
    await send("Page.enable");
    await send("Runtime.enable");
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("页面加载超时")), timeoutMs);
      socket.addEventListener("message", (event) => {
        const payload = JSON.parse(event.data);
        if (payload.method === "Page.loadEventFired") {
          clearTimeout(timer);
          resolve();
        }
      });
    });
  });
}

async function navigate(wsUrl, url, timeoutMs) {
  await withSocket(wsUrl, timeoutMs, async (socket, send) => {
    await send("Page.enable");
    await send("Page.navigate", { url });
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("页面跳转超时")), timeoutMs);
      socket.addEventListener("message", (event) => {
        const payload = JSON.parse(event.data);
        if (payload.method === "Page.loadEventFired") {
          clearTimeout(timer);
          resolve();
        }
      });
    });
  });
}

async function evaluate(wsUrl, expression, timeoutMs) {
  return withSocket(wsUrl, timeoutMs, async (_socket, send) => {
    const response = await send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (response.exceptionDetails) {
      throw new Error(response.exceptionDetails.text || "页面解析脚本执行失败");
    }
    return response.result?.result?.value || [];
  });
}

function withSocket(wsUrl, timeoutMs, handler) {
  return new Promise((resolve, reject) => {
    const socket = new MinimalWebSocket(wsUrl);
    let nextId = 1;
    const pending = new Map();
    const timer = setTimeout(() => {
      socket.close();
      reject(new Error("CDP WebSocket 超时"));
    }, timeoutMs);

    socket.addEventListener("open", async () => {
      try {
        const result = await handler(socket, send);
        clearTimeout(timer);
        socket.close();
        resolve(result);
      } catch (error) {
        clearTimeout(timer);
        socket.close();
        reject(error);
      }
    });
    socket.addEventListener("message", (event) => {
      const payload = JSON.parse(event.data);
      if (!payload.id || !pending.has(payload.id)) return;
      const { resolve: resolvePending, reject: rejectPending } = pending.get(payload.id);
      pending.delete(payload.id);
      if (payload.error) rejectPending(new Error(payload.error.message));
      else resolvePending(payload);
    });
    socket.addEventListener("error", () => reject(new Error("CDP WebSocket 连接失败")));

    function send(method, params = {}) {
      const id = nextId;
      nextId += 1;
      socket.send(JSON.stringify({ id, method, params }));
      return new Promise((resolvePending, rejectPending) => {
        pending.set(id, { resolve: resolvePending, reject: rejectPending });
      });
    }
  });
}

class MinimalWebSocket extends EventEmitter {
  constructor(wsUrl) {
    super();
    this.url = new URL(wsUrl);
    this.buffer = Buffer.alloc(0);
    this.socket = connect(Number(this.url.port || 80), this.url.hostname);
    this.socket.once("connect", () => this.handshake());
    this.socket.on("data", (chunk) => this.read(chunk));
    this.socket.on("error", () => this.emit("error"));
    this.socket.on("close", () => this.emit("close"));
  }

  addEventListener(event, listener) {
    this.on(event, listener);
  }

  send(message) {
    const payload = Buffer.from(message);
    const header = [];
    header.push(0x81);
    if (payload.length < 126) {
      header.push(0x80 | payload.length);
    } else if (payload.length < 65536) {
      header.push(0x80 | 126, (payload.length >> 8) & 0xff, payload.length & 0xff);
    } else {
      throw new Error("WebSocket payload too large");
    }
    const mask = randomBytes(4);
    const masked = Buffer.alloc(payload.length);
    for (let index = 0; index < payload.length; index += 1) {
      masked[index] = payload[index] ^ mask[index % 4];
    }
    this.socket.write(Buffer.concat([Buffer.from(header), mask, masked]));
  }

  close() {
    this.socket.end();
  }

  handshake() {
    this.key = randomBytes(16).toString("base64");
    this.socket.write([
      `GET ${this.url.pathname}${this.url.search} HTTP/1.1`,
      `Host: ${this.url.host}`,
      "Upgrade: websocket",
      "Connection: Upgrade",
      `Sec-WebSocket-Key: ${this.key}`,
      "Sec-WebSocket-Version: 13",
      "\r\n",
    ].join("\r\n"));
  }

  read(chunk) {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    if (!this.opened) {
      const headerEnd = this.buffer.indexOf("\r\n\r\n");
      if (headerEnd < 0) return;
      const header = this.buffer.slice(0, headerEnd).toString("utf8");
      if (!header.includes(" 101 ")) {
        this.emit("error");
        return;
      }
      this.validateAccept(header);
      this.opened = true;
      this.buffer = this.buffer.slice(headerEnd + 4);
      this.emit("open");
    }
    this.readFrames();
  }

  validateAccept(header) {
    const expected = createHash("sha1")
      .update(`${this.key}258EAFA5-E914-47DA-95CA-C5AB0DC85B11`)
      .digest("base64");
    if (!header.toLowerCase().includes(`sec-websocket-accept: ${expected}`.toLowerCase())) {
      throw new Error("WebSocket handshake validation failed");
    }
  }

  readFrames() {
    while (this.buffer.length >= 2) {
      const first = this.buffer[0];
      const second = this.buffer[1];
      const opcode = first & 0x0f;
      let offset = 2;
      let length = second & 0x7f;
      if (length === 126) {
        if (this.buffer.length < 4) return;
        length = this.buffer.readUInt16BE(2);
        offset = 4;
      } else if (length === 127) {
        if (this.buffer.length < 10) return;
        const high = this.buffer.readUInt32BE(2);
        const low = this.buffer.readUInt32BE(6);
        length = high * 2 ** 32 + low;
        offset = 10;
      }
      if (this.buffer.length < offset + length) return;
      const payload = this.buffer.slice(offset, offset + length);
      this.buffer = this.buffer.slice(offset + length);
      if (opcode === 1) this.emit("message", { data: payload.toString("utf8") });
      if (opcode === 8) this.close();
    }
  }
}

async function fetchJson(url) {
  const response = await fetch(url, { method: url.includes("/json/new?") ? "PUT" : "GET" });
  if (!response.ok) throw new Error(`${response.status} ${url}`);
  return response.json();
}

async function writeJson(path, value) {
  await import("node:fs/promises").then(({ mkdir }) => mkdir(dirname(path), { recursive: true }));
  await writeFile(path, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function printReport(report, path) {
  for (const item of report.results) {
    const status = item.count >= report.minResults ? "PASS" : "FAIL";
    console.log(`${status} ${item.keyword}: ${item.count}`);
    for (const offer of item.sample) {
      console.log(`  - ${offer.title} ${offer.priceText || ""}`);
    }
  }
  console.log(`Report: ${path}`);
}

function terminateChrome(chrome) {
  if (chrome.exitCode !== null || chrome.signalCode !== null) return Promise.resolve();
  return new Promise((resolve) => {
    chrome.once("exit", resolve);
    chrome.kill("SIGTERM");
    setTimeout(resolve, 3000);
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

await main();
