/**
 * wayfern_demo.mjs — 连上 Donut 已启动的 Profile，做拟人化操作并读回它对外呈现的指纹。
 *
 * 为什么是 JS：拟人化库只有 npm 包 `wayfern`（`wayfern@0.1.1`，MIT，peerDependency
 * `playwright>=1.20`），它的 `chromium.connectOverCDP()` 会自动给每个 Page 装拟人化钩子。
 * 上游那个 `donutbrowser/wayfern-humanizer` GitHub 仓库并不存在（404），这个包就是它。
 *
 * 依赖：
 *   npm i playwright wayfern
 *   # 连 Donut 的 Wayfern 时不需要下载 Playwright 自带内核
 *
 * 用法：
 *   python3 -m donutkit api run <profile-id> --url https://example.com
 *   node wayfern_demo.mjs http://127.0.0.1:<remote_debugging_port> [目标 URL]
 *   node wayfern_demo.mjs http://127.0.0.1:60991 --keep      # 不关闭自己开的 tab
 *
 * 三条实测出来的硬约束（这台机器上验证过，不是推测）
 * -----------------------------------------------------------------------------
 * 1. **出口 IP 必须用浏览器栈测。** Playwright 的 `context.request` / `page.request`
 *    在 connectOverCDP 下走的是 Node 的网络栈，读出来的是你本机的 IP（实测：本机
 *    IPv6 vs 浏览器 BR 代理）。所以这里用 `page.goto(trace)` + CDP
 *    `DOM.getOuterHTML` 读纯文本，全程走浏览器自己的代理链。
 *
 * 2. **免费计划下引擎会拒绝脚本执行。** `Runtime.evaluate` 直接回
 *    `Browser automation requires a paid Donut Browser plan.`，
 *    `Wayfern.getFingerprint` 回 `Custom fingerprints require a Donut Browser plan
 *    that includes them.`。于是 `page.evaluate` / `locator.fill` / `page.screenshot`
 *    这类高层 API 会以 “Execution context was destroyed” 或超时的形式失败。
 *    本脚本因此把「读指纹」做成三级降级，并把引擎的原话原样打印出来。
 *
 * 3. **不要动用户已有的 tab。** 脚本自己 `newPage()`，结束时只关自己这一个；
 *    已有页面全程不导航、不点击。
 */

import { chromium, wayfern } from "wayfern";

const args = process.argv.slice(2);
const flags = new Set(args.filter((a) => a.startsWith("--")));
const positional = args.filter((a) => !a.startsWith("--"));
const cdpUrl = positional[0];
const targetUrl = positional[1] || "https://example.com";
const KEEP_TAB = flags.has("--keep");

if (!cdpUrl || !/^https?:\/\//.test(cdpUrl)) {
  console.error(
    [
      "用法: node wayfern_demo.mjs <cdp-http-url> [目标 URL] [--keep]",
      "",
      "  cdp-http-url 形如 http://127.0.0.1:60991（Donut 的 remote_debugging_port）",
      "  例: node wayfern_demo.mjs http://127.0.0.1:60991 https://example.com",
      "",
      "注意：Playwright 的 connectOverCDP 吃的是 http 地址，不是 ws://。",
    ].join("\n"),
  );
  process.exit(2);
}

const report = (step, data) => console.log(JSON.stringify({ step, ...data }, null, 2));

/** 把不带 JS 的 DOM 读成文本（免费计划也能用） */
async function domText(session) {
  const doc = await session.send("DOM.getDocument", { depth: -1, pierce: false });
  const html = await session.send("DOM.getOuterHTML", { nodeId: doc.root.nodeId });
  return String(html.outerHTML || "").replace(/<[^>]+>/g, " ");
}

async function main() {
  const browser = await chromium.connectOverCDP(cdpUrl);
  const context = browser.contexts()[0];
  if (!context) throw new Error("这个 CDP 端点没有 context，确认传的是浏览器级地址");
  report("connected", {
    cdpUrl,
    version: browser.version(),
    existingPages: context.pages().length,
  });

  // 自己开一个 tab —— 用户已有的 Gmail / Claude / 账户页面一律不碰
  const page = await context.newPage();
  const session = await context.newCDPSession(page);
  const wfp = wayfern(page);
  const capabilities = {};

  try {
    // ---------------------------------------------------------------- 1. 出口
    // 走浏览器自己的网络栈（因此走 profile 的代理/VPN），再读 DOM —— 不需要 JS
    let exit = null;
    try {
      await page.goto("https://www.cloudflare.com/cdn-cgi/trace", {
        waitUntil: "commit",
        timeout: 45000,
      });
      await page.waitForTimeout(3500);
      const text = await domText(session);
      const pairs = Object.fromEntries(
        text
          .split(/\s+/)
          .filter((w) => /^[a-z_]+=/.test(w))
          .map((w) => [w.slice(0, w.indexOf("=")), w.slice(w.indexOf("=") + 1)]),
      );
      exit = { ip: pairs.ip, country: pairs.loc, colo: pairs.colo, http: pairs.http };
      report("exit", exit);
      capabilities.domRead = true;
    } catch (e) {
      report("exit", { error: String(e).message ?? String(e) });
    }

    // ------------------------------------------------------------ 2. 指纹读回
    // 三级降级：Wayfern.getFingerprint → Wayfern.getIdentity → page.evaluate
    let device = null;
    try {
      device = { source: "Wayfern.getFingerprint", ...(await session.send("Wayfern.getFingerprint")) };
    } catch (e1) {
      report("fingerprint/getFingerprint", { ok: false, engineSays: String(e1.message ?? e1) });
      try {
        const id = await session.send("Wayfern.getIdentity");
        const fields = Object.keys(id.identity || {});
        report("fingerprint/getIdentity", {
          ok: true,
          identityId: id.identityId,
          deviceFields: fields.length,
          note:
            fields.length === 0
              ? "引擎只给了 identityId，设备字段为空 —— 免费计划不提供指纹编辑能力，这是授权边界不是 bug"
              : "identity 里带设备字段",
          ...(fields.length ? { sample: Object.fromEntries(fields.slice(0, 12).map((k) => [k, id.identity[k]])) } : {}),
        });
      } catch (e2) {
        report("fingerprint/getIdentity", { ok: false, engineSays: String(e2.message ?? e2) });
      }

      try {
        device = {
          source: "page.evaluate",
          ...(await page.evaluate(() => ({
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            language: navigator.language,
            languages: navigator.languages,
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            timezoneOffsetMinutes: new Date().getTimezoneOffset(),
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory ?? null,
            webdriver: navigator.webdriver,
            screen: {
              width: screen.width,
              height: screen.height,
              availWidth: screen.availWidth,
              availHeight: screen.availHeight,
              colorDepth: screen.colorDepth,
            },
            devicePixelRatio: window.devicePixelRatio,
            plugins: navigator.plugins.length,
            canvasNoise: (() => {
              const draw = () => {
                const c = document.createElement("canvas");
                c.width = 200;
                c.height = 40;
                const x = c.getContext("2d");
                x.textBaseline = "top";
                x.font = "14px Arial";
                x.fillStyle = "#f60";
                x.fillRect(0, 0, 120, 20);
                x.fillStyle = "#069";
                x.fillText("donut-probe", 2, 4);
                return c.toDataURL().slice(-48);
              };
              return draw() !== draw();
            })(),
          }))),
        };
        capabilities.jsEvaluate = true;
      } catch (e3) {
        report("fingerprint/evaluate", {
          ok: false,
          engineSays: String(e3.message ?? e3),
          meaning:
            "Runtime.evaluate 被引擎拒绝 = 这台机器上的套餐不含 browserAutomation；" +
            "Playwright 的 fill/screenshot/evaluate 都会因此失败，但 Input/DOM/截图类原始 CDP 仍可用",
        });
      }
    }
    if (device) {
      report("fingerprint", device);
      capabilities.fingerprintRead = true;
    }

    // -------------------------------------------------------------- 3. 一致性
    if (device && device.timezone) {
      report("consistency", {
        fingerprintTimezone: device.timezone,
        fingerprintLanguage: device.language,
        exitIP: exit?.ip ?? null,
        exitCountry: exit?.country ?? null,
        timezoneMatchesKnownExit:
          exit?.country === "BR" ? device.timezone === "America/Sao_Paulo" : null,
        note: "对不上不要在这里硬改：REST 上没有写指纹位置的端点，用 donutkit 的 DonutClient.realign_after_rotation()",
      });
    }

    // ---------------------------------------------------------- 4. 拟人化操作
    await page.goto(
      "data:text/html;charset=utf-8," +
        encodeURIComponent('<html><body><h1>humanizer</h1><input id="q" type="text"></body></html>'),
      { timeout: 30000 },
    );
    await page.waitForTimeout(500);
    const typing = { steps: [] };
    try {
      await wfp.move(160, 220);
      typing.steps.push("wfp.move ok");
      await wfp.scroll(0, 140, {});
      typing.steps.push("wfp.scroll ok");
    } catch (e) {
      typing.steps.push(`wfp.move/scroll DENY: ${String(e.message ?? e).slice(0, 120)}`);
    }
    try {
      await wfp.typeText("donut humanizer check", { wpm: 82, errors: true, clear: true });
      typing.steps.push("wfp.typeText dispatched");
    } catch (e) {
      typing.steps.push(`wfp.typeText DENY: ${String(e.message ?? e).slice(0, 160)}`);
    }
    // 校验输入值需要读 DOM property，而读 property 要 evaluate —— 没有就说明清楚
    try {
      typing.value = await page.locator("#q").inputValue();
    } catch (e) {
      typing.value = null;
      typing.verifyUnavailable = String(e.message ?? e).split("\n")[0].slice(0, 140);
    }
    report("humanized-input", typing);

    // --------------------------------------------------- 5. 这套套餐能做什么
    const matrix = {};
    for (const [label, method, params] of [
      ["DOM.getDocument", "DOM.getDocument", { depth: 1 }],
      ["Page.captureScreenshot", "Page.captureScreenshot", { format: "png" }],
      ["Runtime.evaluate", "Runtime.evaluate", { expression: "1+1", returnByValue: true }],
      ["Network.getAllCookies", "Network.getAllCookies", {}],
      ["Wayfern.getIdentity", "Wayfern.getIdentity", {}],
    ]) {
      try {
        await session.send(method, params);
        matrix[label] = "OK";
      } catch (e) {
        matrix[label] = String(e.message ?? e).replace(/^.*Protocol error \([^)]*\):\s*/, "").slice(0, 120);
      }
    }
    report("cdp-capabilities", matrix);
  } finally {
    if (!KEEP_TAB) await page.close();
    report("done", {
      closedOwnTab: !KEEP_TAB,
      existingPages: context.pages().length,
      capabilities,
    });
  }
  // browser.close() 只断开 CDP 连接，Donut 托管的浏览器继续运行
  await browser.close();
}

main().catch((err) => {
  console.error("FAILED:", err);
  process.exit(1);
});
