#!/usr/bin/env node

import path from "node:path";
import { fileURLToPath } from "node:url";
import process from "node:process";

import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const baseUrl = process.argv[2] || "http://127.0.0.1:8642/continuity/";
const fixturePath = path.join(__dirname, "panel_browser_smoke_fixtures.js");
const timeoutMs = 15000;

function log(message) {
  process.stdout.write(`${message}\n`);
}

async function expectText(page, selector, text) {
  await page.waitForFunction(
    ({ targetSelector, fragment }) => {
      const node = document.querySelector(targetSelector);
      return Boolean(node && node.textContent && node.textContent.includes(fragment));
    },
    { targetSelector: selector, fragment: text },
    { timeout: timeoutMs },
  );
}

async function expectButtonDisabled(page, selector, disabled) {
  await page.waitForFunction(
    ({ targetSelector, expected }) => {
      const button = document.querySelector(targetSelector);
      return Boolean(button) && button.disabled === expected;
    },
    { targetSelector: selector, expected: disabled },
    { timeout: timeoutMs },
  );
}

async function setValue(page, selector, value) {
  await page.locator(selector).evaluate((node, nextValue) => {
    node.value = nextValue;
    node.dispatchEvent(new Event("input", { bubbles: true }));
    node.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
}

async function submit(page, selector) {
  await page.locator(selector).evaluate((form) => form.requestSubmit());
}

async function installScenario(page, mode) {
  await page.evaluate(async (scenario) => {
    await window.__installContinuityScenario(scenario);
  }, mode);
  await expectText(page, "#action-summary", "Operator action summary");
}

async function runHappyPath(page) {
  log("Running happy-path browser smoke...");
  await installScenario(page, "happy");

  await setValue(page, "#checkpoint-session-id", "sess_source");
  await setValue(page, "#checkpoint-cwd", "/tmp/project");
  await submit(page, "#checkpoint-form");
  await expectText(page, "#action-result", "\"checkpoint_id\": \"ckpt_happy\"");

  await submit(page, "#verify-form");
  await expectText(page, "#action-summary", "Verify is green; rehydrate is the next guarded action.");
  await expectButtonDisabled(page, "#rehydrate-form button[type=\"submit\"]", false);

  await setValue(page, "#rehydrate-session-id", "sess_target");
  await submit(page, "#rehydrate-form");
  await expectText(page, "#action-result", "\"resulting_session_id\": \"sess_target\"");
  await expectText(page, "#smoke-flow-status", "Reused existing target session");
}

async function runStaleRemediation(page) {
  log("Running stale-checkpoint remediation browser smoke...");
  await installScenario(page, "stale");

  await setValue(page, "#checkpoint-session-id", "sess_source");
  await setValue(page, "#checkpoint-cwd", "/tmp/project");
  await submit(page, "#checkpoint-form");
  await expectText(page, "#action-result", "\"checkpoint_id\": \"ckpt_stale_1\"");

  await submit(page, "#verify-form");
  await expectText(page, "#smoke-flow-status", "stale_live_checkpoint");
  await expectText(page, "#action-summary", "Checkpoint must be rerun before verify/rehydrate can continue.");
  await expectButtonDisabled(page, "#rehydrate-form button[type=\"submit\"]", true);

  await submit(page, "#checkpoint-form");
  await expectText(page, "#action-result", "\"checkpoint_id\": \"ckpt_stale_2\"");

  await submit(page, "#verify-form");
  await expectText(page, "#action-summary", "Verify is green; rehydrate is the next guarded action.");
  await expectButtonDisabled(page, "#rehydrate-form button[type=\"submit\"]", false);

  await setValue(page, "#rehydrate-session-id", "sess_target_remediated");
  await submit(page, "#rehydrate-form");
  await expectText(page, "#action-result", "\"resulting_session_id\": \"sess_target_remediated\"");
  await expectText(page, "#smoke-flow-status", "Reused existing target session");
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    log(`Opening ${baseUrl}`);
    await page.goto(baseUrl, { waitUntil: "networkidle", timeout: timeoutMs });
    await page.waitForSelector("#checkpoint-form", { timeout: timeoutMs });
    await page.addScriptTag({ path: fixturePath });

    await runHappyPath(page);
    await runStaleRemediation(page);

    log("Continuity panel browser smoke passed for happy path and stale-checkpoint remediation unlock.");
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exit(1);
});
