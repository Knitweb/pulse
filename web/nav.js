/* Knitweb shared navigation — injects one consistent hop-menu into every page
 * so the site is a single connected whole with no dead ends. Self-contained,
 * dependency-free, idempotent, accessible. Include once per page:
 *     <script src="/nav.js" defer></script>
 */
(function () {
  "use strict";
  if (document.getElementById("kw-nav")) return; // idempotent

  // The whole map — absolute canonical URLs so this exact menu is portable to
  // any host (knitweb.art, 5mart.ml, the repo /web folders) and always links to
  // the same live pages. `match` highlights the active item when served on the
  // canonical host. External properties are marked with ↗.
  var LINKS = [
    { href: "https://knitweb.art/",                          label: "Knitweb",  brand: true, match: /^\/(index\.html)?$/ },
    { href: "https://knitweb.art/demos/",                    label: "Demos",    match: /^\/demos\// },
    { href: "https://knitweb.art/quantum/",                  label: "QuantumV", match: /^\/quantum\// },
    { href: "https://knitweb.art/worlds.html",               label: "WNW",      match: /^\/worlds\.html$/ },
    { href: "https://knitweb.art/docs/serverless-dapp-model.html", label: "Docs", match: /^\/docs\// },
    { href: "https://node.knitweb.art",                      label: "Run a node", ext: true },
    { href: "https://knitweb.github.io/molgang/",            label: "MOLGANG",  ext: true },
    { href: "https://5mart.ml",                              label: "5mart.ml", ext: true }
  ];

  var path = location.pathname.replace(/\/index\.html$/, "/");

  var css = document.createElement("style");
  css.textContent = [
    "#kw-nav{position:sticky;top:0;z-index:9999;display:flex;align-items:center;gap:2px;",
    "  padding:7px 14px;font:600 12px/1.4 'SF Mono',ui-monospace,Menlo,Consolas,monospace;",
    "  background:rgba(10,13,20,.82);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);",
    "  border-bottom:1px solid rgba(120,140,180,.20);overflow-x:auto;white-space:nowrap;scrollbar-width:none}",
    "#kw-nav::-webkit-scrollbar{display:none}",
    "#kw-nav a{color:#93a3bd;text-decoration:none;padding:5px 11px;border-radius:7px;transition:.15s;flex:0 0 auto}",
    "#kw-nav a:hover{color:#eaf1fb;background:rgba(255,255,255,.06)}",
    "#kw-nav a.kw-brand{color:#5fd0a5;font-weight:800;letter-spacing:-.2px;margin-right:6px}",
    "#kw-nav a.kw-active{color:#eaf1fb;background:rgba(95,208,165,.14);box-shadow:inset 0 0 0 1px rgba(95,208,165,.35)}",
    "#kw-nav .kw-ext::after{content:' ↗';color:#78a8ff;font-size:.9em}",
    "#kw-nav .kw-spacer{flex:1 1 auto}"
  ].join("");
  document.head.appendChild(css);

  var nav = document.createElement("nav");
  nav.id = "kw-nav";
  nav.setAttribute("aria-label", "Knitweb site");

  LINKS.forEach(function (l, i) {
    var a = document.createElement("a");
    a.href = l.href;
    a.textContent = l.label;
    if (l.brand) a.className = "kw-brand";
    if (l.ext) { a.className = (a.className ? a.className + " " : "") + "kw-ext"; a.target = "_blank"; a.rel = "noopener"; }
    if (l.match && l.match.test(path)) { a.className = (a.className ? a.className + " " : "") + "kw-active"; a.setAttribute("aria-current", "page"); }
    nav.appendChild(a);
    if (l.brand) { var sp = document.createElement("span"); sp.className = "kw-spacer"; nav.appendChild(sp); }
  });

  document.body.insertBefore(nav, document.body.firstChild);
})();
