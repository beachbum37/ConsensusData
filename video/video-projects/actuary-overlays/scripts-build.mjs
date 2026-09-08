// Emits the overlay compositions. The two lower thirds differ only in their
// text, so they come from one template — keeping the motion identical between
// speakers, which is what makes them read as one system.
import { writeFileSync, mkdirSync } from "node:fs";
mkdirSync("compositions", { recursive: true });

const HEAD = (title, dur) => `<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>${title}</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></scr`+`ipt>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600;700&display=block" rel="stylesheet" />
    <link rel="stylesheet" href="assets/brand-tokens.css" />
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      /* Transparent canvas — these render to WebM with alpha and composite over
         the cut. Never give body a background colour here. */
      html, body { width: 1920px; height: 1080px; overflow: hidden;
                   background: transparent; font-family: var(--font-ui); }`;

const lowerThird = (id, name, role, dur) => `${HEAD(name, dur)}
      #lt { position: absolute; left: 96px; bottom: 132px; display: flex; align-items: stretch; }
      /* Orange spine draws down first, plate wipes out from behind it — one
         gesture rather than two things appearing. */
      #spine { width: 10px; background: var(--brand); transform-origin: 50% 0%; }
      #plate { background: var(--ink); padding: 22px 40px 24px 30px;
        border-top: 1px solid var(--rule); border-right: 1px solid var(--rule);
        border-bottom: 1px solid var(--rule); box-shadow: 0 26px 70px rgba(0,0,0,0.55);
        overflow: hidden; white-space: nowrap; }
      #name { font-size: 56px; font-weight: 800; letter-spacing: -0.02em;
        color: var(--paper); line-height: 1.05; }
      #role { margin-top: 7px; font-family: var(--font-mono); font-size: 25px;
        font-weight: 500; letter-spacing: 0.12em; color: var(--brand); }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="${id}" data-start="0" data-duration="${dur.toFixed(2)}" data-width="1920" data-height="1080">
      <div id="lt">
        <div id="spine"></div>
        <div id="plate"><div id="name">${name}</div><div id="role">${role}</div></div>
      </div>
    </div>
    <script>
      window.__timelines = window.__timelines || {};
      const DUR = ${dur};
      const tl = gsap.timeline({ paused: true });
      // Initial states use gsap.set (immediate), not tl.set at 0: a zero-duration
      // set inside a paused timeline does not apply while the playhead sits at 0,
      // so frame 0 would flash the finished card before it animates in.
      const plate = document.getElementById("plate");
      const w = plate.getBoundingClientRect().width;   // measure before collapsing

      gsap.set("#spine", { scaleY: 0 });
      gsap.set(plate, { width: 0 });
      gsap.set(["#name", "#role"], { opacity: 0, y: 14 });

      tl.to("#spine", { scaleY: 1, duration: 0.28, ease: "power3.out" }, 0);
      tl.to(plate,    { width: w, duration: 0.42, ease: "power4.out" }, 0.18);
      tl.to("#name",  { opacity: 1, y: 0, duration: 0.30, ease: "power2.out" }, 0.42);
      tl.to("#role",  { opacity: 1, y: 0, duration: 0.30, ease: "power2.out" }, 0.52);

      // Out is quicker than in — a lower third should leave without being watched.
      const o = DUR - 0.55;
      tl.to(["#name", "#role"], { opacity: 0, y: -10, duration: 0.20, ease: "power2.in" }, o);
      tl.to(plate,    { width: 0,  duration: 0.30, ease: "power3.in" }, o + 0.12);
      tl.to("#spine", { scaleY: 0, duration: 0.22, ease: "power3.in" }, o + 0.30);

      tl.to({}, { duration: DUR }, 0);
      window.__timelines["${id}"] = tl;
    </scr`+`ipt>
  </body>
</html>
`;

writeFileSync("compositions/lt-kimberly.html",
  lowerThird("lt-kimberly", "Kimberly Archuleta", "HOST", 4.0));
writeFileSync("compositions/lt-micah.html",
  lowerThird("lt-micah", "Micah O'Kray", "ACTUARY", 4.5));
console.log("wrote 2 lower thirds");
