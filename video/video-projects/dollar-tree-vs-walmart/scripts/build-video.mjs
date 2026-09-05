#!/usr/bin/env node
/**
 * Generates the data-driven compositions from data/items.json.
 *
 *   node scripts/build-video.mjs
 *
 * Writes:
 *   compositions/02-items.html   one card per item, all on one GSAP timeline
 *   compositions/03-tally.html   the totals + the payoff number
 *
 * index.html is hand-authored and NOT generated. Because its scene timings
 * depend on the item count, this script verifies them and exits non-zero with
 * the exact numbers to change if they have drifted.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..");

// ---- Timing constants. Change these and re-run; the script tells you what
// ---- index.html then needs to say.
const HOOK_DUR = 3.0;
const ITEM_DUR = 4.0;
const TALLY_DUR = 6.0;

const data = JSON.parse(readFileSync(join(ROOT, "data/items.json"), "utf8"));
const items = data.items;
if (!Array.isArray(items) || items.length === 0) {
  console.error("data/items.json has no items.");
  process.exit(1);
}

const UNVERIFIED = items.filter((i) => !i.verified).length;

// ---- Derived economics -----------------------------------------------------
const money = (n) => "$" + n.toFixed(2);
const unitStr = (n) => "$" + (n < 0.1 ? n.toFixed(3) : n.toFixed(2));

const rows = items.map((it, i) => {
  for (const side of ["dollarTree", "walmart"]) {
    const s = it[side];
    if (!s || typeof s.price !== "number" || typeof s.size !== "number" || s.size <= 0) {
      console.error(`item ${i} ("${it.name}") has a bad ${side} price/size`);
      process.exit(1);
    }
  }
  const ua = it.dollarTree.price / it.dollarTree.size;
  const ub = it.walmart.price / it.walmart.size;
  const ratio = Math.max(ua, ub) / Math.min(ua, ub);
  const even = ratio < 1.05;
  return {
    ...it,
    idx: i,
    unitA: ua,
    unitB: ub,
    winner: even ? "even" : ua < ub ? "a" : "b",
    ratio,
  };
});

const totalA = rows.reduce((s, r) => s + r.dollarTree.price, 0);
const totalB = rows.reduce((s, r) => s + r.walmart.price, 0);
const winsA = rows.filter((r) => r.winner === "a").length;
const winsB = rows.filter((r) => r.winner === "b").length;
const evens = rows.filter((r) => r.winner === "even").length;

// The sticker totals are NOT comparable — Walmart's packages are bigger, so a
// bigger total is expected and means nothing on its own. The honest number is
// the basket normalized to equal quantity: take the Dollar Tree quantity of
// each item and price it at Walmart's unit price. Positive dtAdvantage means
// Dollar Tree is genuinely cheaper for the amount you actually walk out with.
const sameQtyAtWalmart = rows.reduce((s, r) => s + r.unitB * r.dollarTree.size, 0);
const dtAdvantage = sameQtyAtWalmart - totalA;

const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const pad2 = (n) => String(n).padStart(2, "0");
const SAMPLE_BADGE = UNVERIFIED > 0
  ? '<div class="sample-badge">SAMPLE DATA · NOT REAL PRICES</div>'
  : "";

// ---- Shared CSS ------------------------------------------------------------
const SHARED_CSS = `
    @import url("assets/brand-tokens.css");
    .sample-badge {
      position: absolute; top: 34px; left: 50%; transform: translateX(-50%);
      font-family: var(--font-mono); font-size: 20px; font-weight: 700;
      letter-spacing: 0.22em; color: var(--warn);
      border: 2px solid var(--warn); border-radius: 999px;
      padding: 10px 26px; background: rgba(249, 115, 22, 0.1);
      z-index: 200;
    }`;

// ============================================================================
// 02-items.html
// ============================================================================
const ITEMS_DUR = +(items.length * ITEM_DUR).toFixed(2);

const cardHtml = rows.map((r) => {
  const i = r.idx;
  const verdictWho =
    r.winner === "even" ? "ABOUT EVEN" : r.winner === "a" ? "DOLLAR TREE" : "WALMART";
  const verdictDetail =
    r.winner === "even"
      ? "within 5% per " + esc(r.unit)
      : r.ratio.toFixed(1) + "× cheaper per " + esc(r.unit);
  return `
      <div class="card" id="card-${i}">
        <div class="card-top">
          <span class="idx">${pad2(i + 1)} / ${pad2(items.length)}</span>
          <span class="cat">${esc(String(r.category).toUpperCase())}</span>
        </div>
        <div class="name" id="name-${i}">${esc(r.name)}</div>

        <div class="panel panel-a" id="pan-${i}-a">
          <div class="store">DOLLAR TREE</div>
          <div class="price" id="p-${i}-a">$0.00</div>
          <div class="size">${esc(r.dollarTree.label)}</div>
          <div class="unit" id="u-${i}-a">${unitStr(r.unitA)}<span> / ${esc(r.unit)}</span></div>
        </div>

        <div class="vs" id="vs-${i}">VS</div>

        <div class="panel panel-b" id="pan-${i}-b">
          <div class="store">WALMART</div>
          <div class="price" id="p-${i}-b">$0.00</div>
          <div class="size">${esc(r.walmart.label)}</div>
          <div class="unit" id="u-${i}-b">${unitStr(r.unitB)}<span> / ${esc(r.unit)}</span></div>
        </div>

        <div class="verdict verdict-${r.winner}" id="v-${i}">
          <span class="v-who">${verdictWho}</span>
          <span class="v-detail">${verdictDetail}</span>
        </div>
      </div>`;
}).join("\n");

// Generated timeline JS. Written with double-quoted strings only, so nothing
// here collides with the template literals building it.
const cardJs = rows.map((r) => {
  const i = r.idx;
  const t = +(i * ITEM_DUR).toFixed(2);
  const a = r.dollarTree.price.toFixed(2);
  const b = r.walmart.price.toFixed(2);
  return [
    `        // ---- card ${i + 1}: ${r.name} (local ${t.toFixed(2)}s) ----`,
    `        card(${i}, ${t}, ${a}, ${b});`,
  ].join("\n");
}).join("\n");

const itemsHtml = `<template id="items-template">
  <div
    data-composition-id="items"
    data-start="0"
    data-duration="${ITEMS_DUR}"
    data-width="1080"
    data-height="1920"
  >
    ${SAMPLE_BADGE}
    <div class="whip" id="items-whip"></div>
${cardHtml}

    <style>${SHARED_CSS}
      [data-composition-id="items"] {
        position: absolute; inset: 0; overflow: hidden;
        background: var(--bg); font-family: var(--font-ui); color: var(--text);
      }
      [data-composition-id="items"] .card {
        position: absolute; inset: 0; opacity: 0;
      }
      [data-composition-id="items"] .card-top {
        position: absolute; top: 150px; left: 0; right: 0;
        display: flex; justify-content: center; gap: 22px;
        font-family: var(--font-mono); font-size: 26px; font-weight: 600;
        letter-spacing: 0.24em;
      }
      [data-composition-id="items"] .idx { color: var(--text-dim); }
      [data-composition-id="items"] .cat { color: var(--accent); }
      [data-composition-id="items"] .name {
        position: absolute; top: 216px; left: 60px; right: 60px;
        text-align: center; font-size: 96px; font-weight: 900;
        letter-spacing: -0.03em; line-height: 1.02;
        background: linear-gradient(180deg, #ffffff 0%, #c3ccd8 62%, #ffffff 100%);
        -webkit-background-clip: text; background-clip: text; color: transparent;
        text-shadow: 0 0 40px rgba(255, 255, 255, 0.22);
      }
      [data-composition-id="items"] .panel {
        position: absolute; left: 70px; right: 70px; height: 460px;
        border-radius: 40px; background: var(--bg-panel);
        border: 2px solid var(--hairline);
        padding: 40px 48px;
        display: flex; flex-direction: column; justify-content: center;
      }
      [data-composition-id="items"] .panel-a {
        top: 430px;
        border-color: rgba(34, 197, 94, 0.45);
        background: linear-gradient(180deg, var(--side-a-dim), var(--bg-panel) 70%);
      }
      [data-composition-id="items"] .panel-b {
        top: 1010px;
        border-color: rgba(59, 130, 246, 0.45);
        background: linear-gradient(180deg, var(--side-b-dim), var(--bg-panel) 70%);
      }
      [data-composition-id="items"] .store {
        font-family: var(--font-mono); font-size: 28px; font-weight: 700;
        letter-spacing: 0.2em; margin-bottom: 10px;
      }
      [data-composition-id="items"] .panel-a .store { color: var(--side-a); }
      [data-composition-id="items"] .panel-b .store { color: var(--side-b); }
      [data-composition-id="items"] .price {
        font-family: var(--font-mono); font-size: 138px; font-weight: 700;
        letter-spacing: -0.04em; line-height: 1;
      }
      [data-composition-id="items"] .size {
        font-size: 32px; color: var(--text-muted); margin-top: 6px;
      }
      [data-composition-id="items"] .unit {
        position: absolute; right: 48px; bottom: 40px;
        font-family: var(--font-mono); font-size: 46px; font-weight: 700;
        text-align: right;
      }
      [data-composition-id="items"] .panel-a .unit { color: var(--side-a); }
      [data-composition-id="items"] .panel-b .unit { color: var(--side-b); }
      [data-composition-id="items"] .unit span {
        font-size: 26px; font-weight: 500; color: var(--text-dim);
      }
      [data-composition-id="items"] .vs {
        position: absolute; top: 906px; left: 50%; transform: translateX(-50%);
        width: 108px; height: 108px; border-radius: 50%;
        background: var(--bg); border: 2px solid var(--hairline);
        display: flex; align-items: center; justify-content: center;
        font-family: var(--font-mono); font-size: 34px; font-weight: 700;
        color: var(--text-muted); z-index: 5;
      }
      [data-composition-id="items"] .verdict {
        position: absolute; top: 1560px; left: 70px; right: 70px;
        border-radius: 32px; padding: 30px 40px;
        display: flex; flex-direction: column; align-items: center; gap: 8px;
      }
      [data-composition-id="items"] .verdict-a {
        background: var(--side-a-dim); border: 2px solid var(--side-a);
      }
      [data-composition-id="items"] .verdict-b {
        background: var(--side-b-dim); border: 2px solid var(--side-b);
      }
      [data-composition-id="items"] .verdict-even {
        background: rgba(148, 163, 184, 0.12); border: 2px solid var(--text-dim);
      }
      [data-composition-id="items"] .v-who {
        font-size: 58px; font-weight: 900; letter-spacing: -0.02em;
      }
      [data-composition-id="items"] .verdict-a .v-who { color: var(--side-a); }
      [data-composition-id="items"] .verdict-b .v-who { color: var(--side-b); }
      [data-composition-id="items"] .verdict-even .v-who { color: var(--text-muted); }
      [data-composition-id="items"] .v-detail {
        font-family: var(--font-mono); font-size: 30px; color: var(--text-muted);
      }
      [data-composition-id="items"] .whip {
        position: absolute; top: 0; left: -40%; width: 60%; height: 100%;
        background: linear-gradient(90deg, transparent,
          rgba(255, 255, 255, 0.9), transparent);
        filter: blur(30px); opacity: 0; z-index: 50;
      }
    </style>

    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"><\/script>
    <script>
      (() => {
        window.__timelines = window.__timelines || {};
        const tl = gsap.timeline({ paused: true });
        const root = "[data-composition-id='items']";
        const q = (s) => document.querySelector(root + " " + s);

        // Count a price up from 0. Driven purely by timeline progress, so it is
        // deterministic under seek — the renderer scrubs rather than plays.
        function countTo(sel, target, at, dur) {
          const el = q(sel);
          const proxy = { v: 0 };
          tl.to(proxy, {
            v: target, duration: dur, ease: "power2.out",
            onUpdate: () => { el.textContent = "$" + proxy.v.toFixed(2); },
          }, at);
        }

        // One card's beat map. Every offset below is relative to the card's
        // own start, so retiming the sequence means changing ITEM_DUR only.
        function card(i, t, priceA, priceB) {
          const c = root + " #card-" + i;

          tl.set(c, { opacity: 1 }, t);
          tl.from(c, { y: 70, filter: "blur(16px)", duration: 0.42, ease: "power3.out" }, t);

          // whip covers the cut into the card
          tl.set(root + " #items-whip", { xPercent: 0, opacity: 0 }, t);
          tl.to(root + " #items-whip",
            { xPercent: 280, opacity: 1, duration: 0.26, ease: "power3.in" }, t);
          tl.to(root + " #items-whip", { opacity: 0, duration: 0.14 }, t + 0.26);

          tl.from(c + " .card-top",
            { y: -20, opacity: 0, duration: 0.3, ease: "expo.out" }, t + 0.12);
          tl.from(c + " .name",
            { scale: 1.22, opacity: 0, filter: "blur(20px)", duration: 0.46, ease: "power4.out" },
            t + 0.18);

          // Panels arrive one at a time — the comparison only reads if the eye
          // lands on side A before side B exists.
          tl.from(c + " .panel-a",
            { x: -70, opacity: 0, duration: 0.4, ease: "power3.out" }, t + 0.55);
          countTo("#p-" + i + "-a", priceA, t + 0.62, 0.5);

          tl.from(c + " .vs",
            { scale: 0, opacity: 0, duration: 0.3, ease: "back.out(2.4)" }, t + 0.95);

          tl.from(c + " .panel-b",
            { x: 70, opacity: 0, duration: 0.4, ease: "power3.out" }, t + 1.05);
          countTo("#p-" + i + "-b", priceB, t + 1.12, 0.5);

          // Unit prices are the actual argument — hold them after both stickers.
          tl.from(c + " .unit",
            { y: 18, opacity: 0, duration: 0.34, stagger: 0.1, ease: "power2.out" }, t + 1.75);

          // Verdict slams last, on the beat.
          tl.from(c + " .verdict",
            { scale: 0.82, opacity: 0, duration: 0.36, ease: "back.out(1.8)" }, t + 2.3);

          // Out — leave the frame clean before the next card lands.
          tl.to(c, { opacity: 0, scale: 0.97, filter: "blur(12px)", duration: 0.28,
            ease: "power2.in" }, t + ${ITEM_DUR} - 0.3);
        }

${cardJs}

        // Duration anchor (Render Contract rule 7).
        tl.to({}, { duration: ${ITEMS_DUR} }, 0);
        window.__timelines["items"] = tl;
      })();
    <\/script>
  </div>
</template>
`;

writeFileSync(join(ROOT, "compositions/02-items.html"), itemsHtml);

// ============================================================================
// 03-tally.html
// ============================================================================
const cheaperBasket = dtAdvantage > 0 ? "DOLLAR TREE" : "WALMART";
const deltaAbs = Math.abs(dtAdvantage);
const unitWinner = winsB > winsA ? "Walmart" : winsA > winsB ? "Dollar Tree" : null;
// The interesting case is when per-unit wins and the actual basket disagree.
const upsetLine =
  unitWinner && unitWinner.toUpperCase() !== cheaperBasket
    ? "even though " + unitWinner + " won " +
      Math.max(winsA, winsB) + " of " + items.length + " on unit price"
    : "across " + items.length + " items, same quantities";

const tallyHtml = `<template id="tally-template">
  <div
    data-composition-id="tally"
    data-start="0"
    data-duration="${TALLY_DUR.toFixed(2)}"
    data-width="1080"
    data-height="1920"
  >
    ${SAMPLE_BADGE}
    <div class="t-kicker" id="t-kicker">THE RECEIPT</div>

    <div class="t-row t-row-a" id="t-row-a">
      <span class="t-store">DOLLAR TREE</span>
      <span class="t-total" id="t-total-a">$0.00</span>
    </div>
    <div class="t-row t-row-b" id="t-row-b">
      <span class="t-store">WALMART</span>
      <span class="t-total" id="t-total-b">$0.00</span>
    </div>

    <div class="t-caveat" id="t-caveat">
      different pack sizes — these two totals are not comparable
    </div>

    <div class="t-wins" id="t-wins">
      <span class="t-win t-win-a">${winsA} cheaper / unit</span>
      <span class="t-win t-win-even">${evens} even</span>
      <span class="t-win t-win-b">${winsB} cheaper / unit</span>
    </div>

    <div class="t-payoff" id="t-payoff">
      <div class="t-payoff-label">SAME QUANTITIES · CHEAPER AT ${cheaperBasket}</div>
      <div class="t-payoff-num" id="t-payoff-num">$0.00</div>
      <div class="t-payoff-sub">${upsetLine}</div>
    </div>

    <div class="t-foot" id="t-foot">Sticker price is not price. Compare per unit.</div>

    <style>${SHARED_CSS}
      [data-composition-id="tally"] {
        position: absolute; inset: 0; overflow: hidden;
        background: var(--bg); font-family: var(--font-ui); color: var(--text);
      }
      [data-composition-id="tally"] .t-kicker {
        position: absolute; top: 250px; left: 0; right: 0; text-align: center;
        font-family: var(--font-mono); font-size: 30px; font-weight: 700;
        letter-spacing: 0.34em; color: var(--accent);
      }
      [data-composition-id="tally"] .t-row {
        position: absolute; left: 70px; right: 70px; height: 150px;
        border-radius: 32px; padding: 0 44px;
        display: flex; align-items: center; justify-content: space-between;
        border: 2px solid var(--hairline);
      }
      [data-composition-id="tally"] .t-row-a {
        top: 356px; border-color: rgba(34, 197, 94, 0.5); background: var(--side-a-dim);
      }
      [data-composition-id="tally"] .t-row-b {
        top: 528px; border-color: rgba(59, 130, 246, 0.5); background: var(--side-b-dim);
      }
      [data-composition-id="tally"] .t-store {
        font-family: var(--font-mono); font-size: 34px; font-weight: 700;
        letter-spacing: 0.16em;
      }
      [data-composition-id="tally"] .t-row-a .t-store { color: var(--side-a); }
      [data-composition-id="tally"] .t-row-b .t-store { color: var(--side-b); }
      [data-composition-id="tally"] .t-total {
        font-family: var(--font-mono); font-size: 82px; font-weight: 700;
        letter-spacing: -0.03em;
      }
      [data-composition-id="tally"] .t-wins {
        position: absolute; top: 774px; left: 70px; right: 70px;
        display: flex; justify-content: space-between;
        font-family: var(--font-mono); font-size: 27px; font-weight: 600;
      }
      [data-composition-id="tally"] .t-caveat {
        position: absolute; top: 700px; left: 70px; right: 70px;
        text-align: center; font-size: 25px; font-style: italic;
        color: var(--text-dim);
      }
      [data-composition-id="tally"] .t-win-a { color: var(--side-a); }
      [data-composition-id="tally"] .t-win-even { color: var(--text-dim); }
      [data-composition-id="tally"] .t-win-b { color: var(--side-b); }
      [data-composition-id="tally"] .t-payoff {
        position: absolute; top: 884px; left: 70px; right: 70px;
        border-radius: 44px; padding: 56px 44px;
        text-align: center; background: rgba(251, 191, 36, 0.1);
        border: 3px solid var(--accent);
      }
      [data-composition-id="tally"] .t-payoff-label {
        font-family: var(--font-mono); font-size: 26px; font-weight: 700;
        letter-spacing: 0.18em; color: var(--accent);
      }
      [data-composition-id="tally"] .t-payoff-num {
        font-family: var(--font-mono); font-size: 200px; font-weight: 700;
        letter-spacing: -0.05em; line-height: 1.05; margin: 12px 0 4px;
      }
      [data-composition-id="tally"] .t-payoff-sub {
        font-size: 34px; color: var(--text-muted);
      }
      [data-composition-id="tally"] .t-foot {
        position: absolute; top: 1560px; left: 70px; right: 70px;
        text-align: center; font-size: 44px; font-weight: 800;
        letter-spacing: -0.02em; color: var(--text);
      }
    </style>

    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"><\/script>
    <script>
      (() => {
        window.__timelines = window.__timelines || {};
        const tl = gsap.timeline({ paused: true });
        const root = "[data-composition-id='tally']";
        const q = (s) => document.querySelector(root + " " + s);

        function countTo(sel, target, at, dur) {
          const el = q(sel);
          const proxy = { v: 0 };
          tl.to(proxy, {
            v: target, duration: dur, ease: "power2.out",
            onUpdate: () => { el.textContent = "$" + proxy.v.toFixed(2); },
          }, at);
        }

        tl.from(root + " .t-kicker",
          { y: -24, opacity: 0, duration: 0.4, ease: "expo.out" }, 0.05);
        tl.from(root + " .t-row-a",
          { x: -80, opacity: 0, duration: 0.42, ease: "power3.out" }, 0.3);
        countTo("#t-total-a", ${totalA.toFixed(2)}, 0.38, 0.6);
        tl.from(root + " .t-row-b",
          { x: 80, opacity: 0, duration: 0.42, ease: "power3.out" }, 0.6);
        countTo("#t-total-b", ${totalB.toFixed(2)}, 0.68, 0.6);
        tl.from(root + " .t-caveat",
          { opacity: 0, duration: 0.34, ease: "power2.out" }, 1.0);
        tl.from(root + " .t-wins",
          { opacity: 0, y: 16, duration: 0.34, ease: "power2.out" }, 1.15);

        // The payoff card is the whole point of the video — give it room.
        tl.from(root + " .t-payoff",
          { scale: 0.86, opacity: 0, filter: "blur(14px)",
            duration: 0.55, ease: "back.out(1.6)" }, 1.5);
        countTo("#t-payoff-num", ${deltaAbs.toFixed(2)}, 1.75, 0.9);

        tl.from(root + " .t-foot",
          { y: 24, opacity: 0, duration: 0.42, ease: "power3.out" }, 2.7);

        // Outro holds ~3s so the number is readable and the frame breathes.
        tl.to({}, { duration: ${TALLY_DUR.toFixed(2)} }, 0);
        window.__timelines["tally"] = tl;
      })();
    <\/script>
  </div>
</template>
`;

writeFileSync(join(ROOT, "compositions/03-tally.html"), tallyHtml);

// ============================================================================
// Verify index.html timings match the generated durations
// ============================================================================
const itemsStart = HOOK_DUR;
const tallyStart = +(HOOK_DUR + ITEMS_DUR).toFixed(2);
const total = +(tallyStart + TALLY_DUR).toFixed(2);

const idx = readFileSync(join(ROOT, "index.html"), "utf8");
const expect = [
  ["scene-items", `data-start="${itemsStart.toFixed(2)}"`],
  ["scene-items", `data-duration="${ITEMS_DUR.toFixed(2)}"`],
  ["scene-tally", `data-start="${tallyStart.toFixed(2)}"`],
  ["scene-tally", `data-duration="${TALLY_DUR.toFixed(2)}"`],
  ["root",        `data-duration="${total.toFixed(2)}"`],
];
const missing = expect.filter(([, attr]) => !idx.includes(attr));

console.log("");
console.log("  compositions/02-items.html   " + items.length + " cards · " + ITEMS_DUR + "s");
console.log("  compositions/03-tally.html   " + TALLY_DUR.toFixed(2) + "s");
console.log("");
console.log("  Dollar Tree sticker total    " + money(totalA));
console.log("  Walmart sticker total        " + money(totalB));
console.log("  Per-unit wins                DT " + winsA + " · WM " + winsB + " · even " + evens);
console.log("  Same quantities at WM        " + money(sameQtyAtWalmart) +
  "  (vs " + money(totalA) + " at DT)");
console.log("  → cheaper at                 " + cheaperBasket + " by " + money(deltaAbs));
console.log("");
if (UNVERIFIED > 0) {
  console.log("  ⚠ " + UNVERIFIED + "/" + items.length +
    " items are unverified — SAMPLE DATA badge is stamped on every frame.");
  console.log("    Replace data/items.json with real receipt numbers before publishing.");
  console.log("");
}
if (missing.length) {
  console.error("  ✗ index.html timings are stale. It must contain:");
  for (const [what, attr] of missing) console.error("      " + attr + "   (on #" + what + ")");
  process.exit(1);
}
console.log("  ✓ index.html timings match. Total runtime " + total.toFixed(2) + "s.");
console.log("");
