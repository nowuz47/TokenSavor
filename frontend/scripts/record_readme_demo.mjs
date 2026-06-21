import { chromium } from "playwright-core";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";
import os from "node:os";

const repoRoot = process.env.SCROOGE_REPO_ROOT
  ? path.resolve(process.env.SCROOGE_REPO_ROOT)
  : path.resolve(process.cwd(), "..");
const frontendDir = path.join(repoRoot, "frontend");
const backendDir = path.join(repoRoot, "backend");
const assetsDir = path.join(repoRoot, "docs", "assets");
const distDir = path.join(frontendDir, "dist");
const videoPath = path.join(assetsDir, "scrooge-readme-demo.webm");
const tempVideoDir = path.join(os.tmpdir(), `scrooge-demo-video-${Date.now()}`);
const tempDbPath = path.join(os.tmpdir(), `scrooge-demo-${Date.now()}.db`);
const apiPort = 8771;
const uiPort = 1431;
const apiBase = `http://127.0.0.1:${apiPort}`;
const uiBase = `http://127.0.0.1:${uiPort}`;
const pythonExe = path.join(backendDir, ".venv", "Scripts", "python.exe");
const tscBin = path.join(frontendDir, "node_modules", "typescript", "bin", "tsc");
const viteJs = path.join(frontendDir, "node_modules", "vite", "bin", "vite.js");
const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const demoCsvPath = path.join(tempVideoDir, "orders-demo.csv");

await fs.mkdir(assetsDir, { recursive: true });
await fs.mkdir(tempVideoDir, { recursive: true });
await fs.writeFile(demoCsvPath, buildDemoCsv(), "utf8");

const children = [];
let staticServer;

try {
  await runCommand(process.execPath, [tscBin], {
    cwd: frontendDir,
    env: { ...process.env, VITE_SCROOGE_API_BASE: apiBase },
    label: "tsc"
  });
  await runCommand(process.execPath, [viteJs, "build"], {
    cwd: frontendDir,
    env: { ...process.env, VITE_SCROOGE_API_BASE: apiBase },
    label: "vite"
  });

  const backend = spawn(
    pythonExe,
    ["-m", "uvicorn", "scrooge.main:app", "--host", "127.0.0.1", "--port", String(apiPort)],
    {
      cwd: backendDir,
      env: {
        ...process.env,
        SCROOGE_DB_PATH: tempDbPath,
        SCROOGE_SIDECAR_STATUS: "demo",
        SCROOGE_HOTKEY_STATUS: "demo"
      },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true
    }
  );
  pipeChildLogs(backend, "backend");
  children.push(backend);

  staticServer = await startStaticServer(distDir, uiPort);

  await waitForJson(`${apiBase}/health`, 30_000);
  await waitForText(uiBase, 30_000);

  const browser = await chromium.launch({
    executablePath: edgePath,
    headless: false,
    args: ["--window-size=1024,768"]
  });
  const context = await browser.newContext({
    viewport: { width: 1024, height: 768 },
    recordVideo: {
      dir: tempVideoDir,
      size: { width: 1024, height: 768 }
    }
  });
  const page = await context.newPage();
  await page.addInitScript(() => {
    window.localStorage.setItem("scrooge-locale", "en");
    window.localStorage.setItem("scrooge-theme", "dark");
  });

  await page.goto(uiBase, { waitUntil: "networkidle" });
  await page.waitForTimeout(1800);

  await page.locator("textarea.editor-textarea").fill(
    [
      "Analyze the attached orders-demo.csv file.",
      "Find Korean revenue anomalies, preserve region/revenue/error_count,",
      "and return root-cause hypotheses plus recommended checks."
    ].join(" ")
  );
  await page.waitForTimeout(1300);

  await page.locator('input[type="file"]').setInputFiles(demoCsvPath);
  await page.waitForTimeout(1800);

  await page.getByRole("button", { name: /^Optimize$/ }).click();
  await page.waitForSelector(".improvement-panel", { timeout: 15_000 });
  await page.waitForTimeout(4500);

  await page.getByRole("button", { name: "Savings" }).click();
  await page.waitForSelector(".dashboard-status-grid", { timeout: 15_000 });
  await page.waitForTimeout(5000);

  await page.getByRole("button", { name: "History" }).click();
  await page.waitForSelector(".table-card, .activity-list", { timeout: 15_000 });
  await page.waitForTimeout(4000);

  await context.close();
  await browser.close();

  const videos = await findFiles(tempVideoDir, ".webm");
  if (videos.length === 0) {
    throw new Error(`No Playwright video was produced in ${tempVideoDir}`);
  }
  await fs.copyFile(videos[0], videoPath);
  console.log(videoPath);
} finally {
  if (staticServer) {
    await new Promise((resolve) => staticServer.close(resolve));
  }
  for (const child of children.reverse()) {
    if (child.exitCode === null && !child.killed) {
      try {
        child.kill();
      } catch {
        // The process may have already exited between the guard and kill call.
      }
    }
  }
}

async function startStaticServer(rootDir, port) {
  const server = http.createServer(async (request, response) => {
    try {
      const url = new URL(request.url ?? "/", `http://127.0.0.1:${port}`);
      const safePath = path.normalize(decodeURIComponent(url.pathname)).replace(/^(\.\.[/\\])+/, "");
      let filePath = path.join(rootDir, safePath === "/" ? "index.html" : safePath);
      try {
        const stat = await fs.stat(filePath);
        if (stat.isDirectory()) {
          filePath = path.join(filePath, "index.html");
        }
      } catch {
        filePath = path.join(rootDir, "index.html");
      }
      const body = await fs.readFile(filePath);
      response.writeHead(200, { "Content-Type": contentType(filePath) });
      response.end(body);
    } catch (error) {
      response.writeHead(500, { "Content-Type": "text/plain" });
      response.end(String(error));
    }
  });
  await new Promise((resolve) => server.listen(port, "127.0.0.1", resolve));
  return server;
}

function contentType(filePath) {
  if (filePath.endsWith(".html")) return "text/html; charset=utf-8";
  if (filePath.endsWith(".js")) return "text/javascript; charset=utf-8";
  if (filePath.endsWith(".css")) return "text/css; charset=utf-8";
  if (filePath.endsWith(".png")) return "image/png";
  if (filePath.endsWith(".svg")) return "image/svg+xml";
  return "application/octet-stream";
}

async function runCommand(command, args, options) {
  await new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: options.cwd,
      env: options.env,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true
    });
    pipeChildLogs(child, options.label);
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`${options.label} failed with exit code ${code}`));
    });
  });
}

function pipeChildLogs(child, label) {
  child.stdout?.on("data", (chunk) => {
    process.stdout.write(`[${label}] ${chunk}`);
  });
  child.stderr?.on("data", (chunk) => {
    process.stderr.write(`[${label}] ${chunk}`);
  });
}

async function waitForJson(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.json();
    } catch {
      await sleep(500);
    }
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function waitForText(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return await response.text();
    } catch {
      await sleep(500);
    }
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function findFiles(dir, extension) {
  const entries = await fs.readdir(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const child = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...await findFiles(child, extension));
    } else if (child.endsWith(extension)) {
      files.push(child);
    }
  }
  return files;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function buildDemoCsv() {
  const rows = ["region,orders,revenue,error_count"];
  for (let index = 0; index < 260; index += 1) {
    rows.push("KR,120,3810000,0");
  }
  rows.push("KR,7,12000,5");
  rows.push("US,92,2510000,0");
  rows.push("JP,85,2180000,0");
  rows.push("SG,44,930000,1");
  return `${rows.join("\n")}\n`;
}
