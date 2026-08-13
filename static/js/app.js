const NAV = [
  // Main
  { id: "dashboard", label: "Dashboard", icon: "M3 12l9-9 9 9M5 10v10h14V10" },
  { id: "saved", label: "Saved Projects", icon: "M5 3h11l3 3v15a1 1 0 01-1 1H5a1 1 0 01-1-1V4a1 1 0 011-1zM8 3v5h6V3" },
  { id: "market", label: "Market Research", icon: "M3 3v18h18M7 14l4-4 3 3 5-6" },
  { id: "planning", label: "Product Planning", icon: "M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" },
  // Section: Create
  { _section: "Create & Build" },
  { id: "factory", label: "Product Factory", icon: "M3 21h18M5 21V8l5-3 5 3M9 21v-4h4v4M14 21V11l5-3v13" },
  { id: "research", label: "Niche Research", icon: "M11 19a8 8 0 100-16 8 8 0 000 16zM21 21l-4.35-4.35" },
  { id: "ebook", label: "Ebook Builder", icon: "M4 5a2 2 0 012-2h9l5 5v11a2 2 0 01-2 2H6a2 2 0 01-2-2z" },
  { id: "visual", label: "Visual Review", icon: "M4 5a2 2 0 012-2h12a2 2 0 012 2v14a2 2 0 01-2 2H6a2 2 0 01-2-2zM10 9l5 3-5 3z" },
  // Section: Publish
  { _section: "Publish & Sell" },
  { id: "publishing", label: "Publishing Studio", icon: "M6 2h9l5 5v13a2 2 0 01-2 2H6a2 2 0 01-2-2V4a2 2 0 012-2zM8 13h8M8 17h6M8 9h3" },
  { id: "packages", label: "Platform Packages", icon: "M21 8l-9-5-9 5m18 0l-9 5m9-5v8l-9 5m0-13L3 8m9 5v8M3 8v8l9 5" },
  { id: "ad", label: "Ad Generator", icon: "M4 8h16M4 8l2 11h12l2-11M9 3h6l1 5H8z" },
  // Section: Account
  { _section: "Account" },
  { id: "subscription", label: "Subscription", icon: "M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" },
];
const TITLES = { dashboard: "Dashboard", saved: "Saved Projects", market: "Market Research", planning: "Product Planning", factory: "Product Factory", research: "Niche Research", ebook: "Ebook Builder", "ebook-workspace": "Ebook Project", visual: "Visual Review", publishing: "Publishing Studio", packages: "Platform Packages", ad: "Ad Generator", subscription: "Subscription Plans" };

const MARKET_PRODUCT_TYPES = [
  "Ebook", "Workbook", "Checklist", "Coloring Book", "Word Search Book",
  "Crossword Puzzle Book", "Flip Book", "Math Worksheet", "Spelling Worksheet",
  "Planner", "Not Sure Yet",
];

let current = "dashboard";
let factoryType = null;
// Workflow lineage: ids of the record being advanced into the next stage, so the
// generated plan/product UPDATES the existing project instead of creating a new one.
let pendingProductProjectId = null;
// Researched product brief attached when arriving from "Build Product" (ebook path).
// Carries the full project data through to the Ebook Builder view so the contract
// reaches generate_ebook and the brief is visible to the user while they edit.
let pendingEbookBrief = null;

const YN = ["No", "Yes"];

const PRODUCT_TYPES = [
  {
    id: "ebook",
    label: "Ebook",
    icon: "M4 5a2 2 0 012-2h9l5 5v11a2 2 0 01-2 2H6a2 2 0 01-2-2z",
    desc: "Structured, sellable ebook",
    fields: [
      { name: "ebook_title", label: "Ebook title", type: "text", required: true },
      { name: "author_brand", label: "Author name", type: "text", required: true, placeholder: "e.g. Jordan Lee" },
      { name: "topic", label: "Topic / niche", type: "text", required: true },
      { name: "audience", label: "Target audience", type: "text" },
      { name: "chapters", label: "Number of chapters", type: "number", value: "6" },
      { name: "tone", label: "Tone", type: "select", options: ["Professional", "Friendly", "Motivational", "Educational", "Simple and beginner-friendly"] },
      { name: "reading_level", label: "Reading level", type: "select", options: ["6th grade", "8th grade", "General adult"] },
      {
        name: "use_research",
        label: "Use latest research notes",
        type: "select",
        options: YN,
        default: "No",
        hint: "Set Yes after Niche Research → Send to Ebook Builder, or paste notes below.",
      },
      {
        name: "research_notes",
        label: "Research notes (optional)",
        type: "textarea",
        placeholder: "Paste findings/sources. Chapters will paraphrase these — never copy.",
      },
      { name: "include_worksheets", label: "Include worksheets", type: "select", options: YN },
      { name: "include_images", label: "Include visuals (charts/photos)", type: "select", options: YN, default: "Yes" },
    ],
  },
  {
    id: "coloring_book",
    label: "Coloring Book",
    icon: "M12 19l7-7 3 3-7 7-3-3zM18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z",
    desc: "Retail-ready cover + coloring pages",
    guide:
      "Easy path: add a title and theme, keep Sellable AI artwork, then click Generate. " +
      "Story-style books use 3 quick approvals (cover → one sample page → full book) so you don’t waste credits.",
    fields: [
      {
        name: "coloring_title",
        label: "Book title",
        type: "text",
        required: true,
        placeholder: "e.g. Ocean Friends Coloring Book",
      },
      {
        name: "theme",
        label: "Theme or story",
        type: "text",
        required: true,
        placeholder: "e.g. Cute ocean animals for kids ages 4–8",
        hint: "Describe who/what appears and the setting. More detail = better pages.",
      },
      {
        name: "output_format",
        label: "What do you want to make?",
        type: "select",
        options: [
          { value: "Digital Book", label: "Full coloring book (cover + pages)" },
          { value: "Single Sheet", label: "One single coloring page" },
        ],
        default: "Digital Book",
      },
      {
        name: "quality_mode",
        label: "Artwork quality",
        type: "select",
        options: [
          { value: "AI Image Coloring Page", label: "Sellable AI artwork (recommended)" },
          { value: "Basic Test Fallback", label: "Quick test layout only (not for sale)" },
        ],
        default: "AI Image Coloring Page",
        hint: "Use Sellable AI artwork for a real product. Quick test skips AI images.",
      },
      { name: "age_group", label: "Who is this for?", type: "select", options: ["Kids", "Children ages 8–12", "Teens", "12-adult", "Adults", "All ages"], default: "Children ages 8–12" },
      { name: "pages", label: "Number of pages", type: "number", value: "25", hint: "Thunder Volt full story books use 25 interiors (+ cover = 26 PDF pages)." },
      { name: "art_style", label: "Art style", type: "select", options: ["Cartoon comic-book", "Bold & Easy Kawaii", "Cute cartoon", "Bold KDP style", "Realistic", "Kids coloring"], default: "Cartoon comic-book" },
      { name: "include_captions", label: "Add short captions under pages?", type: "select", options: YN, default: "No" },
      { name: "page_size", label: "Page size", type: "select", options: ["US Letter", "A4", "6x9", "8.5x11"], default: "US Letter" },
    ],
  },
  {
    id: "word_search",
    label: "Word Search Book",
    icon: "M4 4h16v16H4zM8 4v16M4 8h16",
    desc: "Themed word-search puzzles",
    fields: [
      { name: "book_title", label: "Book title", type: "text", required: true },
      { name: "subtitle", label: "Subtitle", type: "text" },
      { name: "theme", label: "Theme / niche", type: "text", required: true },
      { name: "audience", label: "Target age group", type: "text" },
      { name: "output_format", label: "Output format", type: "select", options: ["Single page", "Single Worksheet", "Full Book"] },
      { name: "creation_mode", label: "Word source", type: "select", options: ["Topic (AI generates words)", "Custom word list"] },
      { name: "custom_words", label: "Custom words (one per line)", type: "textarea" },
      { name: "puzzles", label: "Number of puzzles", type: "number", value: "5" },
      { name: "words_per_puzzle", label: "Words per puzzle", type: "number", value: "10" },
      { name: "grid_size", label: "Grid size", type: "select", options: ["12x12 (fewer words)", "15x15 (standard)", "18x18 (more words)"] },
      { name: "difficulty", label: "Difficulty level", type: "select", options: ["Easy", "Medium", "Hard"] },
      { name: "include_answer_key", label: "Include answer key", type: "select", options: YN, default: "Yes" },
      { name: "include_cover", label: "Include cover page", type: "select", options: YN, default: "Yes" },
    ],
  },
  {
    id: "crossword",
    label: "Crossword Puzzle Book",
    icon: "M4 4h16v16H4zM4 10h16M10 4v16",
    desc: "Clues, answers, keys",
    fields: [
      { name: "book_title", label: "Book title", type: "text", required: true, autocomplete: "off" },
      { name: "theme", label: "Theme / niche", type: "text", required: true, autocomplete: "off" },
      { name: "audience", label: "Target age group", type: "text", autocomplete: "off" },
      { name: "output_format", label: "Output format", type: "select", options: ["Full Book", "Single Worksheet", "Single page"], default: "Full Book" },
      { name: "creation_mode", label: "Word source", type: "select", options: ["Topic (AI generates words)", "Custom word list"] },
      { name: "custom_words", label: "Custom words (one per line)", type: "textarea" },
      {
        name: "puzzles",
        label: "Number of puzzles",
        type: "number",
        value: "12",
        autocomplete: "off",
        hint: "Full Book is fixed at 12 puzzles (1 cover + 12 puzzles + 12 answer keys = 25 pages).",
      },
      { name: "difficulty", label: "Difficulty level", type: "select", options: ["Easy", "Medium", "Hard"] },
      { name: "clue_style", label: "Clue style", type: "select", options: ["Easy", "Educational", "Trivia", "Bible-based", "Vocabulary"] },
      { name: "include_answer_key", label: "Include answer key", type: "select", options: YN, default: "Yes" },
      { name: "include_cover", label: "Include cover page", type: "select", options: YN, default: "Yes" },
    ],
  },
  {
    id: "flip_book",
    label: "Flip Book",
    icon: "M12 4v16M4 6h6a2 2 0 012 2M20 6h-6a2 2 0 00-2 2",
    desc: "Page-by-page storyboard",
    hidden: true,
    fields: [
      { name: "flip_title", label: "Flip book title", type: "text", required: true },
      { name: "topic", label: "Story idea / theme", type: "text", required: true },
      { name: "audience", label: "Target audience", type: "text" },
      { name: "scenes", label: "Number of scenes", type: "number", value: "12" },
      { name: "character_style", label: "Character style", type: "select", options: ["Realistic", "Cartoon", "Minimalist", "No characters"] },
      { name: "visual_style", label: "Visual style", type: "select", options: ["Modern", "Vintage", "Whimsical", "Bold and simple"] },
      { name: "page_size", label: "Page size", type: "select", options: ["US Letter", "A4", "6x9", "8.5x11"] },
    ],
  },
  {
    id: "cover_design",
    label: "Cover Design",
    icon: "M4 4h16v16H4zM4 15l4-4 4 4 4-5 4 5M9 9a1.5 1.5 0 100-3 1.5 1.5 0 000 3z",
    desc: "Production-ready cover brief",
    hidden: true,
    fields: [
      { name: "product_title", label: "Product title", type: "text", required: true },
      { name: "subtitle", label: "Subtitle", type: "text" },
      { name: "product_type", label: "Product type", type: "text" },
      { name: "audience", label: "Target audience", type: "text" },
      { name: "cover_style", label: "Cover style", type: "select", options: ["Modern", "Bold", "Minimal", "Colorful", "Luxury", "KDP paperback", "Etsy digital product"] },
      { name: "page_size", label: "Size / format", type: "select", options: ["US Letter", "A4", "6x9", "8.5x11", "Square"] },
    ],
  },
  {
    id: "math_worksheet",
    label: "Math Worksheet",
    icon: "M5 3h14v18H5zM8 7h8M8 11h8M8 15h5",
    desc: "Grades 1-12, with answer key",
    fields: [
      { name: "worksheet_title", label: "Worksheet title", type: "text", required: true },
      { name: "grade", label: "Grade level", type: "select", options: ["Grade 1", "Grade 2", "Grade 3", "Grade 4", "Grade 5", "Grade 6", "Grade 7", "Grade 8", "Grade 9", "Grade 10", "Grade 11", "Grade 12"] },
      { name: "math_topic", label: "Math topic", type: "select", options: ["Addition", "Subtraction", "Multiplication", "Division", "Fractions", "Decimals", "Algebra", "Geometry", "Word Problems"] },
      { name: "output_format", label: "Output format", type: "select", options: ["Single Worksheet", "Full Workbook"] },
      { name: "worksheets", label: "Number of worksheets", type: "number", value: "5" },
      { name: "problems", label: "Problems per worksheet", type: "number", value: "10" },
      { name: "difficulty", label: "Difficulty level", type: "select", options: ["Easy", "Medium", "Hard"] },
      { name: "include_answer_key", label: "Include answer key", type: "select", options: YN, default: "Yes" },
      { name: "include_challenge", label: "Include challenge problems", type: "select", options: YN, default: "No" },
      { name: "page_size", label: "Page size", type: "select", options: ["US Letter", "A4", "6x9", "8.5x11"] },
    ],
  },
  {
    id: "spelling_worksheet",
    label: "Spelling Worksheet",
    icon: "M3 5h18M3 9h18M3 13h18M3 17h18",
    desc: "Themed spelling practice sheets",
    // No passing end-to-end acceptance contract in acceptance_manifest.json
    // (lifecycle/handoff mapping only). Keep code; hide from public picker.
    hidden: true,
    fields: [
      { name: "worksheet_title", label: "Worksheet title", type: "text", required: true },
      { name: "creation_mode", label: "Word source", type: "select", options: ["Themed (AI generates words)", "My custom word list"] },
      { name: "theme", label: "Theme / topic", type: "text", required: true },
      { name: "custom_words", label: "Custom words (one per line)", type: "textarea" },
      { name: "grade", label: "Grade level", type: "select", options: ["Grade 1", "Grade 2", "Grade 3", "Grade 4", "Grade 5", "Grade 6", "Grade 7", "Grade 8"] },
      { name: "word_count", label: "Words per worksheet", type: "number", value: "10" },
      { name: "activity_type", label: "Activity type", type: "select", options: ["Word List", "Unscramble", "Missing Letters", "Fill in the Blank"] },
      { name: "difficulty", label: "Difficulty level", type: "select", options: ["Easy", "Medium", "Hard"] },
      { name: "include_answer_key", label: "Include answer key", type: "select", options: YN, default: "Yes" },
    ],
  },
  {
    id: "planner",
    label: "Planner",
    icon: "M19 3H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V5a2 2 0 00-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z",
    desc: "Daily, weekly, or themed planner pages",
    hidden: true,
    fields: [
      { name: "planner_title", label: "Planner title", type: "text", required: true },
      { name: "planner_type", label: "Planner type", type: "select", options: ["Daily Planner", "Weekly Planner", "Monthly Planner", "Goal Planner", "Budget Planner", "Fitness Planner", "Meal Planner", "Faith Planner", "Business Planner", "Student Planner"] },
      { name: "theme", label: "Theme / niche", type: "text" },
      { name: "audience", label: "Target audience", type: "text" },
      { name: "pages", label: "Number of pages", type: "number", value: "30" },
      { name: "page_size", label: "Page size", type: "select", options: ["US Letter", "A4", "6x9", "8.5x11", "A5"] },
      { name: "interior_style", label: "Interior style", type: "select", options: ["Minimal", "Modern", "Elegant", "Fun and colorful", "Black and white KDP style"] },
      { name: "include_cover", label: "Include cover page", type: "select", options: YN, default: "Yes" },
      { name: "include_toc", label: "Include table of contents", type: "select", options: YN, default: "Yes" },
      { name: "include_notes", label: "Include notes pages", type: "select", options: YN, default: "Yes" },
      { name: "include_habit_tracker", label: "Include habit tracker", type: "select", options: YN, default: "Yes" },
      { name: "include_calendar", label: "Include calendar pages", type: "select", options: YN, default: "Yes" },
      { name: "include_reflection", label: "Include reflection pages", type: "select", options: YN, default: "Yes" },
      { name: "output_format", label: "Output", type: "select", options: ["PDF", "ZIP Package"] },
    ],
  },
  {
    id: "marketing_kit",
    label: "Marketing Kit",
    icon: "M11 5H6a2 2 0 012-2v11a2 2 0 012-2zm9 0h-4v11a2 2 0 01-2 2v-11zM3 3h18v18H3V3z",
    desc: "Copy, descriptions, and ad scripts",
    hidden: true,
    fields: [
      { name: "product_name", label: "Product name", type: "text", required: true },
      { name: "product_type", label: "Product type", type: "text", required: true },
      { name: "audience", label: "Target audience", type: "text" },
      { name: "platforms", label: "Platforms", type: "text" },
      { name: "include_description", label: "Include product description", type: "select", options: YN, default: "Yes" },
      { name: "include_sales_page", label: "Include sales page copy", type: "select", options: YN, default: "Yes" },
      { name: "include_social", label: "Include social media captions", type: "select", options: YN, default: "Yes" },
      { name: "include_email", label: "Include email promo", type: "select", options: YN, default: "Yes" },
      { name: "include_ad_script", label: "Include ad script", type: "select", options: YN, default: "Yes" },
    ],
  },
];

function productType(id) {
  return PRODUCT_TYPES.find((t) => t.id === id);
}

// ---------- helpers ----------
async function api(path, opts) {
  let res;
  try {
    res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...opts,
    });
  } catch (err) {
    throw new Error(
      "Could not reach the server. Make sure the Flask app is running, then try again."
    );
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status})`);
  return data;
}

function toast(msg, type = "ok") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className =
    "fixed bottom-5 right-5 z-50 rounded-xl px-4 py-3 text-sm text-white shadow-lg " +
    (type === "error" ? "bg-rose-600" : "bg-emerald-600");
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3200);
}

function md(text) {
  return marked.parse(text || "");
}

function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

/** Persistable product payload: drop UI-only `_` keys and non-JSON values. */
function productSavePayload(d, { omitPdfBytes = false } = {}) {
  // Preview data-URLs / huge base64 blobs break Save (multi‑MB JSON POST).
  // PDF bytes can also be ~30MB+ for AI coloring books — prefer package_id on disk.
  const omitKeys = new Set([
    "cover_preview_b64",
    "sample_preview_b64",
    "paid_api_warning",
  ]);
  if (omitPdfBytes) omitKeys.add("pdf_bytes");

  const body = Object.fromEntries(
    Object.entries(d || {}).filter(([k, v]) => {
      if (k.startsWith("_")) return false;
      if (omitKeys.has(k)) return false;
      if (typeof v === "function") return false;
      // Drop DOM / non-serializable leftovers
      if (v && typeof v === "object") {
        if (typeof Node !== "undefined" && v instanceof Node) return false;
      }
      return true;
    })
  );
  markUserSaved(body);
  return body;
}

function _estimateJsonBytes(obj) {
  try {
    return new Blob([JSON.stringify(obj)]).size;
  } catch (e) {
    return Number.MAX_SAFE_INTEGER;
  }
}

function safeUrl(s) {
  try {
    const u = new URL(String(s || ""), window.location.origin);
    return u.protocol === "http:" || u.protocol === "https:" ? u.href : "";
  } catch {
    return "";
  }
}

function spinner(label) {
  return `<div class="rounded-2xl border border-slate-200 bg-white p-8 flex items-center gap-3 text-slate-500">
    <svg class="animate-spin h-5 w-5 text-brand-600" viewBox="0 0 24 24" fill="none">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z"></path>
    </svg>${label}</div>`;
}

function card(inner) {
  return `<div class="rounded-2xl border border-slate-200 bg-white p-6">${inner}</div>`;
}

function saveBar(type, getPayload) {
  const btn = document.createElement("button");
  btn.className = "btn-primary";
  btn.textContent = "Save as Project";
  btn.onclick = async () => {
    const name = prompt("Name this project:");
    if (!name) return;
    try {
      const payload = getPayload();
      const existingId = payload && payload._project_id != null ? payload._project_id : null;
      const { _project_id, ...body } = payload || {};
      markUserSaved(body);
      const saved = existingId != null
        ? await api(`/projects/${existingId}`, { method: "PUT", body: JSON.stringify({ name, type, data: body }) })
        : await api("/projects", { method: "POST", body: JSON.stringify({ name, type, data: body }) });
      if (payload && saved && saved.id != null) payload._project_id = saved.id;
      toast(existingId != null ? "Project updated" : "Project saved");
      loadProjects();
    } catch (e) {
      toast(e.message, "error");
    }
  };
  const wrap = document.createElement("div");
  wrap.className = "flex justify-end";
  wrap.appendChild(btn);
  return wrap;
}

// ---------- navigation ----------
function buildNav() {
  const nav = document.getElementById("nav");
  const mobile = document.getElementById("mobileNav");
  nav.innerHTML = "";
  mobile.innerHTML = "";
  NAV.forEach((item) => {
    // Section header
    if (item._section) {
      const hdr = document.createElement("div");
      hdr.className = "px-3 pt-4 pb-1 text-[10px] font-bold uppercase tracking-widest text-brand-400";
      hdr.textContent = item._section;
      nav.appendChild(hdr);
      return;
    }
    const a = document.createElement("div");
    a.className = "nav-link" + (item.id === current ? " active" : "");
    a.dataset.go = item.id;
    a.innerHTML = `<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${item.icon}"/></svg>${item.label}`;
    a.onclick = () => go(item.id);
    nav.appendChild(a);

    const opt = document.createElement("option");
    opt.value = item.id;
    opt.textContent = item.label;
    mobile.appendChild(opt);
  });
  mobile.value = current;
  mobile.onchange = (e) => go(e.target.value);
}

function go(view) {
  // Stale lineage must never bleed across navigations; runNextAction/sendToBuilder
  // re-set this AFTER calling go() for the step that needs it.
  pendingProductProjectId = null;
  current = view;
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("hidden", v.dataset.view !== view));
  document.getElementById("pageTitle").textContent = TITLES[view];
  buildNav();
  if (view === "dashboard") loadDashboard();
  if (view === "saved") loadProjects();
  if (view === "factory") buildFactoryTypes();
  if (view === "market") initMarket();
  if (view === "planning") { planLineageId = null; initPlanTypes(); loadPlanSources(); }
  if (view === "visual") initVisual();
  if (view === "publishing") initPublishing();
  if (view === "packages") initPackages();
}

// ---------- dashboard ----------
async function loadDashboard() {
  // Wire the Saved Projects "show test projects" toggle (one-time, idempotent).
  const tgl = document.getElementById("showTestProjects");
  if (tgl && !tgl.dataset.wired) {
    tgl.addEventListener("change", () => loadProjects());
    tgl.dataset.wired = "1";
  }
  await loadProjects();
}

// Mark a project data blob as user-saved (the user explicitly clicked Save
// in the UI). This sets the visible-by-default flag and strips any test/
// debug flags that might have been inherited from earlier states.
function markUserSaved(data) {
  if (!data || typeof data !== "object") return data;
  data.user_saved = true;
  delete data.system_test;
  delete data.temporary;
  delete data.validation_only;
  delete data.archived;
  data._saved_at = new Date().toISOString();
  return data;
}
// ----- Save consent helpers -----
// Show the "Save or Continue" dialog after a workflow product is generated.
function _showWorkflowSaveDialog(d, onSave) {
  const name = (d.title || "Your product").trim();
  const overlay = document.createElement("div");
  overlay.style = "position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:999;display:flex;align-items:center;justify-content:center;padding:1rem;";
  overlay.innerHTML = '<div style="background:white;border-radius:1rem;padding:1.75rem;max-width:480px;width:100%;box-shadow:0 25px 50px rgba(0,0,0,0.25);font-family:system-ui,sans-serif;">' +
    '<h2 style="font-size:1.125rem;font-weight:700;color:#0f172a;margin:0 0 0.75rem;">Save this product?</h2>' +
    '<p style="color:#475569;font-size:0.9rem;margin:0 0 1.5rem;line-height:1.6;">' +
    '<strong>' + escapeHtml(name) + '</strong> is ready. Would you like to save it to your projects?<br><br>' +
    'Saving unlocks Publishing, Downloads, Sales Pages, and Ad Packages. You can always save it later from the product preview.</p>' +
    '<div style="display:flex;flex-wrap:wrap;gap:0.75rem;justify-content:flex-end;">' +
    '<button id="_dlgCancel" type="button" style="padding:0.625rem 1.25rem;border-radius:0.75rem;border:1px solid #cbd5e1;background:white;color:#475569;font-size:0.875rem;font-weight:500;cursor:pointer;">Cancel</button>' +
    '<button id="_dlgNoSave" type="button" style="padding:0.625rem 1.25rem;border-radius:0.75rem;border:1px solid #cbd5e1;background:white;color:#64748b;font-size:0.875rem;font-weight:500;cursor:pointer;">Continue Without Saving</button>' +
    '<button id="_dlgSave" type="button" style="padding:0.625rem 1.25rem;border-radius:0.75rem;border:none;background:#4f46e5;color:white;font-size:0.875rem;font-weight:600;cursor:pointer;">Save Project</button>' +
    '</div></div>';
  document.body.appendChild(overlay);
  const close = () => { if (overlay.parentNode) document.body.removeChild(overlay); };
  overlay.querySelector("#_dlgSave").onclick = async () => {
    close();
    try {
      await onSave();
    } catch (e) {
      toast(e.message || "Could not save project.", "error");
    }
  };
  overlay.querySelector("#_dlgNoSave").onclick = () => {
    close();
    d._user_declined_save = true;
    toast("You can still preview and download your product here.");
  };
  overlay.querySelector("#_dlgCancel").onclick = () => close();
  overlay.onclick = (e) => { if (e.target === overlay) close(); };
}

// Actually save a workflow product (called after user confirms).
// d._nsRenderPostSave is set by nextStepsPanel() so this can switch the panel UI.
async function _doWorkflowSave(d) {
  if (d._project_id == null) return;
  // Reuse ensureProductSaved so large coloring-book PDFs omit base64 the same way.
  await ensureProductSaved(d);
  if (d._nsRenderPostSave) d._nsRenderPostSave();
  toast("Project saved. Choose your next step.");
}



// Mark a project data blob as system-test / temporary (used by automated test
// scripts so their Saved Projects don't pollute the public list).
function markSystemTest(data, reason) {
  if (!data || typeof data !== "object") return data;
  data.system_test = true;
  data.temporary = true;
  data._test_reason = reason || "automated test";
  data._test_at = new Date().toISOString();
  return data;
}

// Saved Projects visibility:
//   - "user-saved" projects (the only ones visible by default)
//   - test / debug / auto-generated projects (hidden unless the developer
//     toggles "Show test / debug / auto-generated projects" on)
const _TEST_NAME_PATTERNS = /\b(test|workflow\.?test|pipeline\.?test|validation|regression|smoke|qa\.?test|debug|unit\.?test|integration\.?test|bench)\b/i;
function isUserSavedProject(p) {
  if (!p) return false;
  // Explicitly flagged as system/test/temporary → hide.
  if (p.system_test || p.temporary) return false;
  // Explicitly marked as user_saved=True → show.
  if (p.user_saved === true) return true;
  // New-style record explicitly opted out (system_test=False but user_saved=False explicitly) → hide.
  // But check: if user_saved is False and system_test is False, and name looks like test → hide.
  if (p.user_saved === false) {
    // Check name pattern for test/debug detection as safety net
    if (_TEST_NAME_PATTERNS.test(p.name || "")) return false;
    return false; // explicit opt-out
  }
  // Old-style record (no top-level flags): fall back to data-level flags.
  const d = p.data || {};
  if (d.system_test || d.temporary || d.validation_only || d.archived) return false;
  if (d.user_saved === true) return true;
  // Name-based detection as additional safety net for old projects
  if (_TEST_NAME_PATTERNS.test(d.name || "")) return false;
  // Old projects with no explicit flags → show (backward compat).
  return true;
}

// Admin mode: enabled via localStorage or URL ?admin=1
function isAdminMode() {
  return localStorage.getItem("factory_admin_mode") === "true" ||
    new URLSearchParams(window.location.search).has("admin");
}

function setAdminMode(val) {
  localStorage.setItem("factory_admin_mode", val ? "true" : "false");
  refreshAdminControls();
  loadProjects();
}

function refreshAdminControls() {
  const adminSection = document.querySelector(".admin-controls");
  if (!adminSection) return;
  adminSection.classList.toggle("hidden", !isAdminMode());
}

async function loadProjects() {
  const showAll = !!document.getElementById("showTestProjects")?.checked;
  let projects = [];
  try {
    // Backend now filters by default; opt in to all projects when toggle is on.
    const url = showAll ? "/projects?include_system=1" : "/projects";
    projects = await api(url);
  } catch (e) {
    /* ignore */
  }

  const counts = { research: 0, ebook: 0, ad: 0, product: 0, launch: 0 };
  projects.forEach((p) => {
    if (counts[p.type] !== undefined) counts[p.type]++;
    if (p.data && (p.data.launch_package_generated || p.data._launch_package)) counts.launch++;
  });

  // Filter before stats — previously referenced userVisible before init and
  // crashed loadProjects, so Saved Projects never refreshed after Save.
  const userVisible = projects.filter(isUserSavedProject);

  const stats = [
    { label: "Saved Products", value: userVisible.length, accent: "bg-brand-600", sub: "your products" },
    { label: "Factory Products", value: counts.product, accent: "bg-emerald-600", sub: "created" },
    { label: "Promotion Packages", value: counts.ad, accent: "bg-amber-500", sub: "generated" },
    { label: "Launch Packages", value: counts.launch, accent: "bg-violet-600", sub: "generated" },
  ];
  const sc = document.getElementById("statCards");
  if (sc) {
    sc.innerHTML = stats
      .map(
        (s) => `<div class="rounded-2xl border border-slate-200 bg-white p-5">
          <div class="text-2xl font-extrabold text-slate-900 mb-0.5">${s.value}</div>
          <div class="text-sm font-semibold text-slate-700">${s.label}</div>
          <div class="text-xs text-slate-400">${s.sub}</div></div>`
      )
      .join("");
  }

  const emptyMsg = `<p class="text-sm text-slate-400 py-6 text-center">No saved projects yet. Generate something and save it here.</p>`;
  const emptyMsgHidden = `<p class="text-sm text-slate-400 py-6 text-center">No visible projects. Toggle "Show test / debug" to see all.</p>`;

  const recent = document.getElementById("recentList");
  if (recent) {
    if (!userVisible.length) {
      recent.innerHTML = emptyMsg;
    } else {
      recent.innerHTML = "";
      userVisible.slice(0, 5).forEach((p) => recent.appendChild(projectRow(p, { dashboard: true })));
    }
  }

  // Saved Projects page: filter by user_saved unless the developer toggled
  // "Show test / debug / auto-generated projects" on.
  const visible = showAll ? projects : userVisible;

  const saved = document.getElementById("savedList");
  if (saved) {
    if (!visible.length) {
      saved.innerHTML = showAll ? emptyMsgHidden : emptyMsg;
    } else {
      saved.innerHTML = "";
      visible.forEach((p) => saved.appendChild(projectRow(p, { showMeta: showAll })));
    }
  }

  // Admin controls wiring — only runs when admin mode is on.
  // Delete All (admin): backup + type DELETE to confirm.
  const delAllBtn = document.getElementById("deleteAllBtn");
  if (delAllBtn && !delAllBtn.dataset.wired) {
    delAllBtn.addEventListener("click", async () => {
      if (!isAdminMode()) { toast("Admin mode required.", "error"); return; }
      if (delAllBtn.disabled) return;
      const count = visible.length;
      if (count === 0) return;
      // Step 1: confirm count.
      if (!confirm(`Delete all ${count} saved project${count === 1 ? "" : "s"}?\n\nThis creates a backup first. Type DELETE to confirm.`)) return;
      // Step 2: type DELETE to proceed.
      const typed = prompt(`⚠️ This will permanently delete ${count} project${count === 1 ? "" : "s"} from your database.\n\nType DELETE in all caps to confirm:\n`);
      if (typed !== "DELETE") {
        if (typed !== null) toast("Delete cancelled — you must type DELETE exactly.");
        return;
      }
      try {
        delAllBtn.disabled = true;
        delAllBtn.textContent = "Backing up…";
        // Step 3: create backup via backend
        await api("/admin/backup-db", { method: "POST" });
        delAllBtn.textContent = "Deleting…";
        const result = await api("/projects?delete_all=1&user_saved_only=1", { method: "DELETE" });
        toast(`Deleted ${result.deleted || count} saved project${result.deleted === 1 ? "" : "s"}. Backup saved.`);
        loadProjects();
        loadDashboard();
      } catch (e) {
        toast("Delete failed: " + e.message, "error");
        delAllBtn.disabled = false;
        delAllBtn.textContent = "Admin: Delete All Saved Projects";
      }
    });
    delAllBtn.dataset.wired = "1";
  }
  if (delAllBtn) {
    delAllBtn.disabled = !isAdminMode() || showAll || visible.length === 0;
    delAllBtn.title = !isAdminMode()
      ? "Admin mode required"
      : showAll
      ? "Turn off 'Show test / debug' to delete all user-saved projects"
      : visible.length === 0
      ? "No saved projects to delete"
      : `Delete all ${visible.length} saved project${visible.length === 1 ? "" : "s"}`;
  }

  // Delete Test/Debug Projects Only (admin): backup + type DELETE to confirm.
  const delTestBtn = document.getElementById("deleteTestDebugBtn");
  if (delTestBtn && !delTestBtn.dataset.wired) {
    delTestBtn.addEventListener("click", async () => {
      if (!isAdminMode()) { toast("Admin mode required.", "error"); return; }
      const testCount = (projects || []).filter(p => p.system_test || p.temporary || !p.user_saved).length;
      if (testCount === 0) { toast("No test/debug projects to delete."); return; }
      if (!confirm(`Delete ${testCount} test/debug project${testCount === 1 ? "" : "s"}?\n\nThis creates a backup first.`)) return;
      const typed = prompt(`⚠️ This will permanently delete ${testCount} test/debug/temporary project${testCount === 1 ? "" : "s"}.\n\nType DELETE in all caps to confirm:\n`);
      if (typed !== "DELETE") {
        if (typed !== null) toast("Delete cancelled — you must type DELETE exactly.");
        return;
      }
      try {
        delTestBtn.disabled = true;
        delTestBtn.textContent = "Backing up…";
        await api("/admin/backup-db", { method: "POST" });
        delTestBtn.textContent = "Deleting…";
        const result = await api("/admin/delete-test-projects", { method: "DELETE" });
        toast(`Deleted ${result.deleted || testCount} test/debug project${result.deleted === 1 ? "" : "s"}. Backup saved.`);
        loadProjects();
        loadDashboard();
      } catch (e) {
        toast("Delete failed: " + e.message, "error");
        delTestBtn.disabled = false;
        delTestBtn.textContent = "Delete Test/Debug Projects Only";
      }
    });
    delTestBtn.dataset.wired = "1";
  }
  if (delTestBtn) {
    delTestBtn.disabled = !isAdminMode();
  }

  // Admin mode toggle link — appear when NOT in admin mode.
  // (The toggle itself lives in the admin-controls section which is hidden in normal mode)
  const adminHint = document.getElementById("adminModeHint");
  if (adminHint) adminHint.classList.toggle("hidden", isAdminMode());
  // Enable Admin Mode button
  const enableAdminBtn = document.getElementById("enableAdminBtn");
  if (enableAdminBtn && !enableAdminBtn.dataset.wired) {
    enableAdminBtn.addEventListener("click", () => setAdminMode(true));
    enableAdminBtn.dataset.wired = "1";
  }
  // Exit Admin Mode button
  const exitAdminBtn = document.getElementById("exitAdminBtn");
  if (exitAdminBtn && !exitAdminBtn.dataset.wired) {
    exitAdminBtn.addEventListener("click", () => setAdminMode(false));
    exitAdminBtn.dataset.wired = "1";
  }
  // When admin mode is on, the hint is hidden (already toggled above)
}

function projectTypeLabel(p) {
  return p.type === "product"
    ? (p.data && p.data.product_label) || "Product"
    : p.type === "research_plan"
    ? "Research Plan"
    : p.type === "product_plan"
    ? "Product Plan"
    : p.type === "youtube_resource"
    ? "Video Resource"
    : p.type === "publishing_layout"
    ? "Publishing Layout"
    : p.type;
}

// ---------- workflow stages ----------
const STAGE_ORDER = [
  "research_saved", "product_plan_saved", "product_generated",
  "publishing_preview_ready", "export_ready", "completed",
];
const STAGE_LABELS = {
  research_saved: "Research Saved",
  product_plan_saved: "Product Plan Saved",
  product_generated: "Product Generated",
  publishing_preview_ready: "Publishing Preview Ready",
  export_ready: "Export Ready",
  completed: "Completed",
};
const STAGE_BADGE = {
  research_saved: "bg-slate-100 text-slate-700",
  product_plan_saved: "bg-indigo-100 text-indigo-700",
  product_generated: "bg-blue-100 text-blue-700",
  publishing_preview_ready: "bg-amber-100 text-amber-700",
  export_ready: "bg-emerald-100 text-emerald-700",
  completed: "bg-teal-100 text-teal-700",
};

function hasVisualPlan(d) {
  if (!d) return false;
  if (d.preview_html) return true;
  const vp = d.visual_plan;
  if (!vp) return false;
  if (Array.isArray(vp)) return vp.length > 0;
  return Array.isArray(vp.chapters) && vp.chapters.length > 0;
}

// Resolve a project's workflow stage. Type + content give a base stage; a stored
// stage further along the pipeline wins (publishing/export/completed are not
// derivable from content alone). Export artifacts auto-advance to export_ready.
function projectStage(p) {
  const d = p.data || {};
  const stored = STAGE_LABELS[d.stage] ? d.stage : null;
  let derived = null;
  switch (p.type) {
    case "research_plan": derived = "research_saved"; break;
    case "product_plan": derived = "product_plan_saved"; break;
    case "publishing_layout": derived = "publishing_preview_ready"; break;
    case "product":
    case "ebook": {
      const releaseFail = String(d.release_status || "").toUpperCase() === "FAIL";
      const releaseWarn = String(d.release_status || "").toUpperCase() === "WARNING";
      const ebookLike = p.type === "ebook" || String(d.product_type || "").toLowerCase() === "ebook";
      if (ebookLike && (releaseFail || d.export_ready === false || String(d.release_status || "").toUpperCase() === "WARNING")) {
        derived = releaseWarn ? "publishing_preview_ready" : "product_generated";
      } else {
        derived = (d.export_package_id || d.product_exports) ? "export_ready" : "product_generated";
      }
      break;
    }
    default: derived = null;
  }
  if (derived == null) return stored; // research / ad / youtube_resource: no workflow stage
  if (stored && STAGE_ORDER.indexOf(stored) > STAGE_ORDER.indexOf(derived)) return stored;
  return derived;
}

function _isEbookProject(p) {
  if (!p) return false;
  if (p.type === "ebook") return true;
  const pt = String((p.data && p.data.product_type) || "").toLowerCase();
  return pt === "ebook";
}

function nextActionLabel(stage, p) {
  const d = (p && p.data) || {};
  if (_isEbookProject(p) && (d.ebook_project_workspace || d.ebook_workspace)) {
    const next = (d.ebook_workspace && d.ebook_workspace.next_action) || "";
    if (next === "generate_manuscript") return "Generate Manuscript";
    if (next === "approve_manuscript") return "Approve Manuscript";
    if (next === "request_correction") return "Request Correction";
    if (next === "correct_manuscript") return "Request Correction";
    return "Open Ebook Project";
  }
  switch (stage) {
    case "research_saved": return "Create Product Plan";
    case "product_plan_saved": return "Build Product";
    case "product_generated":
      return _isEbookProject(p) ? "Open in Publishing Studio" : "Open in Product Factory";
    case "publishing_preview_ready": return "Export Product";
    case "export_ready": return "Download files";
    case "completed": return "View Completed Package";
    default: return null;
  }
}

// Gate 13: Create Draft Revision (APPROVED only) — Saved Projects actions.
function projectArtifactMeta(p) {
  const d = p && p.data && typeof p.data === "object" ? p.data : {};
  const state = String((p && p.artifact_state) || d.artifact_state || "")
    .trim()
    .toUpperCase();
  const artifactId = String(
    (p && p.artifact_id) || d.artifact_id || d.package_id || ""
  ).trim();
  let revision = 1;
  const rawRev =
    p && p.artifact_revision != null ? p.artifact_revision : d.artifact_revision;
  if (rawRev != null && rawRev !== "") {
    const n = Number(rawRev);
    if (Number.isFinite(n)) revision = Math.max(1, Math.trunc(n));
  }
  return { state, artifactId, revision };
}

function shouldShowCreateDraftRevision(p) {
  return projectArtifactMeta(p).state === "APPROVED";
}

function buildCreateDraftRevisionPayload(p) {
  const meta = projectArtifactMeta(p);
  // Only the four Gate 12 revision keys — no content/assets/cover/exports.
  return {
    create_draft_revision: true,
    reason: "Create draft revision from approved artifact",
    expected_artifact_id: meta.artifactId,
    expected_revision: meta.revision,
  };
}

async function createDraftRevision(p, btn) {
  if (!shouldShowCreateDraftRevision(p)) return;
  if (btn && btn.disabled) return;
  const confirmMsg =
    "Create a draft revision?\n\n" +
    "Your approved version will be preserved. Editing continues in a new draft " +
    "revision — the approved artifact is not replaced.";
  if (!confirm(confirmMsg)) return;
  if (btn && btn.disabled) return;
  setBusyEl(btn, true);
  try {
    const body = buildCreateDraftRevisionPayload(p);
    const res = await fetch(`/projects/${p.id}/revisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (res.status === 409) {
      toast(
        data.error ||
          "This project changed on the server. Reopen it from Saved Projects, then try Create Draft Revision again.",
        "error"
      );
      return;
    }
    if (!res.ok) {
      toast(data.error || `Request failed (${res.status})`, "error");
      return;
    }
    toast("Draft revision created. Your approved version is preserved.");
    const project = await api(`/projects/${p.id}`);
    openProject(project);
    loadProjects();
  } catch (err) {
    toast(
      (err && err.message) || "Could not create draft revision.",
      "error"
    );
  } finally {
    setBusyEl(btn, false);
  }
}

function projectRow(p, opts) {
  const isDash = opts && opts.dashboard;
  const showMeta = opts && opts.showMeta;
  const d = p.data || {};
  const date = new Date(p.updated_at).toLocaleDateString();
  const stage = projectStage(p);
  const nextLabel = nextActionLabel(stage, p);
  const typePill = `<span class="shrink-0 rounded-md bg-brand-100 text-brand-700 text-xs font-semibold px-2 py-1 capitalize">${escapeHtml(projectTypeLabel(p))}</span>`;
  const stageBadge = stage
    ? `<span class="shrink-0 rounded-md ${STAGE_BADGE[stage]} text-xs font-semibold px-2 py-1">${escapeHtml(STAGE_LABELS[stage])}</span>`
    : "";

  let metaBadge = "";
  if (showMeta) {
    if (d.system_test) metaBadge = `<span class="shrink-0 rounded-md bg-rose-100 text-rose-700 text-xs font-semibold px-2 py-1">test</span>`;
    else if (d.temporary) metaBadge = `<span class="shrink-0 rounded-md bg-amber-100 text-amber-700 text-xs font-semibold px-2 py-1">temporary</span>`;
    else if (d.validation_only) metaBadge = `<span class="shrink-0 rounded-md bg-amber-100 text-amber-700 text-xs font-semibold px-2 py-1">validation</span>`;
    else if (d.archived) metaBadge = `<span class="shrink-0 rounded-md bg-slate-200 text-slate-600 text-xs font-semibold px-2 py-1">archived</span>`;
    else if (d.user_saved) metaBadge = `<span class="shrink-0 rounded-md bg-emerald-100 text-emerald-700 text-xs font-semibold px-2 py-1">user-saved</span>`;
  }

  const row = document.createElement("div");
  row.className = "flex items-center justify-between gap-3 rounded-xl border border-slate-100 hover:border-brand-200 hover:bg-brand-50/40 px-4 py-3 transition" + (isDash ? " dashboard-row" : "");

  // Saved Projects only (not dashboard): explicit Create Draft Revision for APPROVED.
  const showDraftRevision = !isDash && shouldShowCreateDraftRevision(p);
  const draftRevisionBtn = showDraftRevision
    ? `<button type="button" class="rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold px-3 py-1.5 disabled:opacity-50" data-create-draft-revision title="Approved version preserved; editing continues in a new draft">Create Draft Revision</button>`
    : "";
  const draftRevisionNote = showDraftRevision
    ? `<span class="hidden xl:inline text-xs text-slate-500 max-w-[14rem] leading-snug" data-draft-revision-note>Approved version preserved; editing continues in a new draft.</span>`
    : "";

  // Download / Launch only apply to finished products. Showing them on
  // product_plan / research rows called /export-product, wrote orphan packages,
  // then /download returned 403 — the classic "Download doesn't work" UX.
  // Ebook Project workspace: PDF/ZIP stay hidden until server preflight PASS.
  const workspaceEbook =
    p.type === "ebook" &&
    (d.ebook_project_workspace || d.ebook_workspace) &&
    !(d.export_ready === true && String(d.release_status || "").toUpperCase() === "PASS");
  const canDownloadProduct =
    (p.type === "product" || p.type === "ebook") && !workspaceEbook;
  const dlPdfBtn = canDownloadProduct
    ? `<button class="rounded-lg ${isDash ? "bg-slate-100 hover:bg-slate-200 text-slate-600" : "bg-emerald-600 hover:bg-emerald-700 text-white"} text-xs font-semibold px-3 py-1.5" data-dl-pdf>${isDash ? "PDF" : "Download PDF"}</button>`
    : "";
  const dlZipBtn = canDownloadProduct && !isDash
    ? `<button class="rounded-lg bg-slate-700 hover:bg-slate-800 text-white text-xs font-semibold px-3 py-1.5" data-dl-zip>Download ZIP</button>`
    : "";
  const launchBtn = canDownloadProduct && !isDash
    ? `<button class="rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold px-3 py-1.5" data-launch>Launch Package</button>`
    : "";

  if (isDash) {
    // Clean dashboard view: title + type + date + Open (+ PDF when downloadable)
    row.innerHTML = `
      <div class="min-w-0 flex items-center gap-3 flex-1">
        ${typePill}
        <span class="truncate font-semibold text-slate-800">${escapeHtml(p.name)}</span>
        <span class="hidden sm:inline text-xs text-slate-400 ml-1">${date}</span>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <button class="rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold px-3 py-1.5" data-open>Open</button>
        ${dlPdfBtn}
      </div>`;
  } else {
    // Full Saved Projects view
    row.innerHTML = `
      <div class="min-w-0 flex items-center gap-3">
        ${typePill}
        ${stageBadge}
        ${metaBadge}
        <span class="truncate font-medium text-slate-800">${escapeHtml(p.name)}</span>
        <span class="hidden sm:inline text-xs text-slate-400">${date}</span>
        ${draftRevisionNote}
      </div>
      <div class="flex items-center gap-2 shrink-0">
        ${dlPdfBtn}
        ${dlZipBtn}
        ${launchBtn}
        ${nextLabel ? `<button class="rounded-lg bg-brand-600 hover:bg-brand-700 text-white text-xs font-semibold px-3 py-1.5" data-next>${escapeHtml(nextLabel)}</button>` : ""}
        ${draftRevisionBtn}
        <button class="text-sm font-medium text-brand-600 hover:text-brand-800" data-open>Open</button>
        <button class="text-sm font-medium text-rose-500 hover:text-rose-700" data-del>Delete</button>
      </div>`;
  }
  // Direct download buttons: call /export-product and triggerDownload. Lazy:
  // only fetch when clicked. For projects that haven't been exported yet, the
  // first click builds the package; subsequent clicks reuse the cached
  // product_exports on the data. Buttons render only for product/ebook rows.
  const dlPdf = row.querySelector("[data-dl-pdf]");
  const dlZip = row.querySelector("[data-dl-zip]");
  async function fetchAndDownload(fileKey, kindLabel) {
    setBusyEl(fileKey === "pdf" ? dlPdf : dlZip, true);
    try {
      const data = (p.data && (p.data.product_exports || p.data.exports)) || {};
      let ex = data.files;
      if (!ex) {
        const r = await api("/export-product", {
          method: "POST",
          body: JSON.stringify({ project_id: p.id }),
        });
        ex = r.exports && r.exports.files;
      }
      const f = ex && ex[fileKey];
      if (f && f.url) {
        await triggerDownload(f.url, f.name || (p.name + "." + fileKey));
        toast(kindLabel + " download started.");
      } else {
        toast(kindLabel + " is not available for this project yet. Open the project to build it.", "error");
      }
    } catch (err) {
      toast("Could not prepare " + kindLabel + ": " + err.message, "error");
    } finally {
      setBusyEl(fileKey === "pdf" ? dlPdf : dlZip, false);
    }
  }
  if (dlPdf) dlPdf.onclick = () => fetchAndDownload("pdf", "PDF");
  if (dlZip) dlZip.onclick = () => fetchAndDownload("zip", "ZIP");
  const lpBtn = row.querySelector("[data-launch]");
  if (lpBtn) lpBtn.onclick = () => renderLaunchPackage(p.id, p.data);
  const nextBtn = row.querySelector("[data-next]");
  if (nextBtn) nextBtn.onclick = () => runNextAction(p);
  const openBtn = row.querySelector("[data-open]");
  if (openBtn) openBtn.onclick = () => openProject(p);
  const draftRevBtn = row.querySelector("[data-create-draft-revision]");
  if (draftRevBtn) {
    draftRevBtn.onclick = () => createDraftRevision(p, draftRevBtn);
  }
  // Dashboard rows omit Delete — must null-check or loadProjects crashes
  // and Saved Projects stays empty even when the project is in the DB.
  const delBtn = row.querySelector("[data-del]");
  if (delBtn) {
    delBtn.onclick = async () => {
      if (!confirm(`Delete "${p.name}"?`)) return;
      try { await api(`/projects/${p.id}`, { method: "DELETE" }); toast("Deleted"); loadProjects(); }
      catch (e) { toast(e.message, "error"); }
    };
  }
  return row;
}

function openProject(p) {
  const d = p.data || {};
  if (p.type === "research") {
    go("research");
    document.getElementById("researchInput").value = d.keyword || "";
    renderResearch(d);
  } else if (p.type === "ebook") {
    if (d.ebook_project_workspace || d.ebook_workspace) {
      openEbookWorkspace(p.id);
      return;
    }
    go("ebook");
    document.getElementById("ebookInput").value = d.source || "";
    renderEbook(d);
  } else if (p.type === "ad") {
    go("ad");
    document.getElementById("adInput").value = d.details || "";
    renderAd(d);
  } else if (p.type === "product") {
    go("factory");
    if (d.product_type && productType(d.product_type)) {
      selectFactoryType(d.product_type);
      const form = document.getElementById("factoryForm");
      Object.entries(d.fields || {}).forEach(([k, v]) => {
        const el = form.elements[k];
        if (el) el.value = v;
      });
      // Re-enforce coloring-book Single Sheet rules after field restore
      if (d.product_type === "coloring_book") _coloringBookSetupForm();
    }
    d._project_id = p.id; // already saved; lets "Send to Publishing Studio" reuse it
    renderProduct(d);
  } else if (p.type === "research_plan") {
    go("market");
    d._source_project_id = p.id; // choosing an idea updates this record in place
    if (d && Array.isArray(d.opportunities) && d.opportunities.length) {
      renderDiscovery(d);
    } else {
      renderMarket(d);
    }
  } else if (p.type === "product_plan") {
    go("planning");
    const form = document.getElementById("planForm");
    Object.entries((d.form) || {}).forEach(([k, v]) => {
      const el = form.elements[k];
      if (el) el.value = v;
    });
    d._project_id = p.id; // re-saving / sending updates this record in place
    renderPlan(d);
  } else if (p.type === "youtube_resource") {
    go("visual");
    renderSavedYtResource(d);
  } else if (p.type === "publishing_layout") {
    go("publishing");
    renderSavedPublishing(d);
  }
}

// Route a project to the correct next step based on its workflow stage, advancing
// the SAME record in place rather than creating a new one.
async function runNextAction(p) {
  const d0 = (p && p.data) || {};
  if (_isEbookProject(p) && (d0.ebook_project_workspace || d0.ebook_workspace)) {
    await openEbookWorkspace(p.id);
    return;
  }
  const stage = projectStage(p);
  if (stage === "research_saved") {
    go("planning");
    await loadPlanSources();
    const sel = document.getElementById("planSource");
    if (sel && sel.querySelector(`option[value="${p.id}"]`)) sel.value = String(p.id);
    prefillPlanFromResearch(p);
    toast("Create the product plan, then send it to the Product Factory.");
  } else if (stage === "product_plan_saved") {
    const planData = (p.data && p.data.plan) ? p.data : { plan: (p.data && p.data.plan) || {} };
    // Mirror sendToBuilder's logic: hidden builders show a clear blocked
    // message; ebook plans reopen in the Ebook Builder with the brief
    // attached; other active types reopen in the Product Factory.
    const resolution = resolveFactoryTypeFromPlan(planData.plan || {});
    if (resolution.status === "hidden") {
      toast(
        resolution.hiddenReason ||
        "This product type is not ready in the public builder yet. This plan is saved here in Saved Projects.",
        "error"
      );
      return;
    }
    if (resolution.factoryId === "ebook") {
      const d = p.data || {};
      d._project_id = p.id;
      pendingEbookBrief = d;
      go("ebook");
      document.getElementById("ebookInput").value = (planData.plan && planData.plan.product_title) || "";
      renderBriefPanel(d);
      // Auto-fire the build from the Saved Projects "Build Product" button.
      // Same one-click behavior as the planning-view path: the user clicked
      // "Build Product" expecting a built ebook, not a second click.
      toast("Building your ebook from the saved plan...");
      runEbook();
    } else {
      go("factory");
      const ok = prefillFactoryFromPlan(planData.plan || {});
      pendingProductProjectId = p.id;
      toast(ok ? "Generate your product to continue." : "Pick a product type to generate your product.");
    }
  } else if (stage === "product_generated") {
    // Ebooks go to Publishing Studio; Factory products reopen where the user can download.
    if (_isEbookProject(p)) {
      await openProductInPublishing(p);
    } else {
      openProject(p);
      toast("Opened in Product Factory — download your PDF when ready.");
    }
  } else if (
    stage === "publishing_preview_ready" ||
    stage === "export_ready" ||
    stage === "completed"
  ) {
    await openProductExport(p);
  }
}

// Finalize a product: marked when the user actually downloads/publishes an export
// (a true completion event), advancing the SAME record to "completed" so its next
// action becomes "View Completed Package".
async function markCompletedById(id) {
  if (id == null) return;
  try {
    const src = await api(`/projects/${id}`);
    if (!src) return;
    const sdata = src.data || {};
    if (sdata.stage === "completed") return;
    sdata.stage = "completed";
    await api(`/projects/${id}`, {
      method: "PUT",
      body: JSON.stringify({ name: src.name, type: src.type, data: sdata }),
    });
    loadProjects();
  } catch (e) {
    /* non-fatal */
  }
}

// "Export Product" / "Download / Publish" / "View Completed Package": land the user
// in the export/download area for the underlying product. A publishing_layout row
// resolves to its source product first so the export buttons are available.
async function openProductExport(p) {
  let target = p;
  if (p.type === "publishing_layout") {
    const sid = p.data && p.data.source_project_id;
    if (sid != null) {
      try { const src = await api(`/projects/${sid}`); if (src) target = src; } catch (e) { /* fall back */ }
    }
  }
  openProject(target);
  if (
    (target.type === "product" || target.type === "ebook") &&
    target.data &&
    target.data._nextStepsResult
  ) {
    await nsExport(target.data);
  }
}

// "Open in Publishing Studio": if an ebook has no visual plan yet, auto-run the
// Visual Enhancement Agent (and persist it to the same record) before publishing.
async function openProductInPublishing(p) {
  const d = p.data || {};
  const isEbook = d.product_type === "ebook" || p.type === "ebook";
  if (isEbook && !hasVisualPlan(d) && (d.content || "").trim()) {
    toast("Adding visuals before opening Publishing Studio...");
    try {
      const enhanced = await api("/enhance-ebook", {
        method: "POST",
        body: JSON.stringify({ title: d.title, content: d.content, fields: d.fields || {} }),
      });
      Object.assign(d, enhanced);
      d.stage = "product_generated";
      const { _project_id, ...body } = d;
      await api(`/projects/${p.id}`, { method: "PUT", body: JSON.stringify({ name: p.name, type: p.type, data: body }) });
      loadProjects();
    } catch (e) {
      toast("Could not add visuals automatically. Opening Publishing Studio anyway.", "error");
    }
  }
  pubState.pendingSourceId = p.id;
  pubState.pendingPrefill = true;
  go("publishing");
}

// ---------- market research ----------
function fillTypeSelect(id, anyLabel) {
  const sel = document.getElementById(id);
  if (!sel || sel.options.length) return;
  let opts = MARKET_PRODUCT_TYPES.map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join("");
  if (anyLabel) opts = `<option value="">${escapeHtml(anyLabel)}</option>` + opts;
  sel.innerHTML = opts;
}

function initMarket() {
  fillTypeSelect("ownProductType", null);
  fillTypeSelect("findProductType", "Any product type");
  showMarketStep("chooser");
}

function showMarketStep(step) {
  document.getElementById("marketChooser").classList.toggle("hidden", step !== "chooser");
  document.getElementById("marketOwn").classList.toggle("hidden", step !== "own");
  document.getElementById("marketFind").classList.toggle("hidden", step !== "find");
}

function scoreColor(score) {
  if (score >= 70) return "bg-emerald-600";
  if (score >= 40) return "bg-amber-500";
  return "bg-rose-500";
}

function chips(items) {
  if (!items || !items.length) return '<span class="text-sm text-slate-400">None</span>';
  return `<div class="flex flex-wrap gap-2">${items
    .map((i) => `<span class="rounded-full bg-slate-100 text-slate-700 text-xs px-3 py-1">${escapeHtml(i)}</span>`)
    .join("")}</div>`;
}

function bullets(items) {
  if (!items || !items.length) return '<p class="text-sm text-slate-400">None</p>';
  return `<ul class="list-disc ml-5 space-y-1 text-sm text-slate-700">${items
    .map((i) => `<li>${escapeHtml(i)}</li>`)
    .join("")}</ul>`;
}

function block(title, inner) {
  return `<div><h4 class="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1.5">${title}</h4>${inner}</div>`;
}

function renderMarket(d) {
  const out = document.getElementById("marketOutput");
  const r = d.report || {};
  const modeBadge =
    d.mode === "live"
      ? '<span class="inline-flex items-center gap-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium px-3 py-1">Live web research</span>'
      : '<span class="inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-700 text-xs font-medium px-3 py-1">AI-estimated research (no live web data)</span>';

  const score = r.opportunity_score || 0;

  const sources = (d.sources || []).length
    ? card(
        `<h3 class="text-base font-bold text-slate-900 mb-3">Sources</h3><div class="space-y-2">${d.sources
          .map(
            (s) => `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener"
              class="block rounded-xl border border-slate-100 hover:border-brand-200 px-4 py-2.5 transition">
              <div class="font-medium text-slate-800 truncate text-sm">${escapeHtml(s.title)}</div>
              <div class="text-xs text-brand-600 truncate">${escapeHtml(s.url)}</div></a>`
          )
          .join("")}</div>`
      )
    : "";

  out.innerHTML =
    card(`
      <div class="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div>
          <div class="text-xs font-medium text-slate-500">Opportunity report</div>
          <div class="text-lg font-bold text-slate-900">${escapeHtml(d.niche)}</div>
        </div>
        <div class="flex items-center gap-3">
          ${modeBadge}
          <div class="flex items-center gap-2">
            <span class="flex h-12 w-12 items-center justify-center rounded-xl ${scoreColor(score)} text-white font-bold text-lg">${score || "?"}</span>
            <div class="text-xs text-slate-500 leading-tight">Opportunity<br/>score / 100</div>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
        ${block("Niche summary", `<p class="text-sm text-slate-700">${escapeHtml(r.niche_summary)}</p>`)}
        ${block("Target audience", `<p class="text-sm text-slate-700">${escapeHtml(r.target_audience)}</p>`)}
        ${block("Common customer problems", bullets(r.customer_problems))}
        ${block("What people may be searching for", chips(r.search_terms))}
        ${block("Suggested product ideas", bullets(r.product_ideas))}
        ${block("Suggested title ideas", chips(r.title_ideas))}
        ${block("Best format recommendation", `<p class="text-sm text-slate-700">${escapeHtml(r.best_format)}</p>`)}
        ${block(
          "At a glance",
          `<div class="flex flex-wrap gap-2 text-xs">
            <span class="rounded-lg bg-brand-50 text-brand-700 px-3 py-1.5">Price: ${escapeHtml(r.price_range) || "n/a"}</span>
            <span class="rounded-lg bg-brand-50 text-brand-700 px-3 py-1.5">Difficulty: ${escapeHtml(r.difficulty) || "n/a"}</span>
            <span class="rounded-lg bg-brand-50 text-brand-700 px-3 py-1.5">Competition: ${escapeHtml(r.competition) || "n/a"}</span>
          </div>`
        )}
        <div class="md:col-span-2">${block("Why this product is worth creating", `<p class="text-sm text-slate-700">${escapeHtml(r.why_worth_creating)}</p>`)}</div>
        <div class="md:col-span-2">${block("Recommended next step", `<p class="text-sm font-medium text-slate-800">${escapeHtml(r.next_step)}</p>`)}</div>
      </div>
    `) + sources;

  const bar = document.createElement("div");
  bar.className = "flex justify-end";
  const btn = document.createElement("button");
  btn.className = "btn-primary";
  btn.textContent = "Create Product Plan";
  btn.onclick = () => createProductPlan(d);
  bar.appendChild(btn);
  out.appendChild(bar);
}

async function createProductPlan(d) {
  const name = (d.report && d.report.title_ideas && d.report.title_ideas[0]) || d.niche;
  try {
    await api("/projects", {
      method: "POST",
      body: JSON.stringify({ name, type: "research_plan", data: d }),
    });
    toast("Saved. Opening it in Product Planning...");
    loadProjects();
    go("planning");
    await loadPlanSources();
    const match = planResearchCache.find((p) => p.type === "research_plan" && p.name === name);
    const sel = document.getElementById("planSource");
    if (match) { sel.value = String(match.id); prefillPlanFromResearch(match); }
  } catch (e) {
    toast(e.message, "error");
  }
}

// Path 1: "I already have a niche" -> research the niche, then recommend
// ranked product opportunities INSIDE that niche.
async function runOwnDiscover() {
  const niche = document.getElementById("ownNiche").value.trim();
  if (!niche) return toast("Enter your niche", "error");
  const topic = document.getElementById("ownTopic").value.trim();
  const audience = document.getElementById("ownAudience").value.trim();
  const product_type = document.getElementById("ownProductType").value;
  const out = document.getElementById("marketOutput");
  out.innerHTML = spinner("Researching product opportunities in your niche...");
  setBusy("ownContinueBtn", true);
  try {
    const data = await api("/discover-products", {
      method: "POST",
      body: JSON.stringify({ niche, audience, product_type, goal: topic }),
    });
    renderDiscovery(data);
  } catch (e) {
    out.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusy("ownContinueBtn", false);
  }
}

// Both paths land here: ranked opportunities + a single best recommendation.
let lastDiscovery = null;

// Shared between the Market Research (discovery) view and the Niche Research view
// so both show identical opportunity + recommendation cards and buttons.
function modeBadgeHtml(mode) {
  return mode === "live"
    ? '<span class="inline-flex items-center gap-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium px-3 py-1">Live web research</span>'
    : '<span class="inline-flex items-center gap-1 rounded-full bg-amber-50 text-amber-700 text-xs font-medium px-3 py-1">AI-estimated research (no live web data)</span>';
}

function opportunityCardsHtml(ops) {
  return ops
    .map((o, i) => {
      const sc = o.opportunity_score || 0;
      return `<div class="rounded-2xl border border-slate-200 bg-white p-5">
        <div class="flex items-start justify-between gap-3 mb-3">
          <div class="flex items-center gap-3 min-w-0">
            <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white text-sm font-bold">${o.rank || i + 1}</span>
            <div class="min-w-0">
              <div class="font-bold text-slate-900 truncate">${escapeHtml(o.product_idea)}</div>
              <div class="text-xs text-slate-500">${escapeHtml(o.product_type)}</div>
            </div>
          </div>
          <span class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${scoreColor(sc)} text-white font-bold">${sc || "?"}</span>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          ${block("Niche", `<p class="text-sm text-slate-700">${escapeHtml(o.niche) || "&mdash;"}</p>`)}
          ${block("Target audience", `<p class="text-sm text-slate-700">${escapeHtml(o.target_audience)}</p>`)}
          ${block("Main customer problem", `<p class="text-sm text-slate-700">${escapeHtml(o.customer_problem)}</p>`)}
          ${block("Recommended sales angle", `<p class="text-sm text-slate-700">${escapeHtml(o.sales_angle)}</p>`)}
          <div class="sm:col-span-2">${block("Why this opportunity is worth considering", `<p class="text-sm text-slate-700">${escapeHtml(o.why_opportunity)}</p>`)}</div>
        </div>
        <div class="mt-3 flex flex-wrap gap-2 text-xs">
          <span class="rounded-lg bg-brand-50 text-brand-700 px-3 py-1.5">Price: ${escapeHtml(o.price_range) || "n/a"}</span>
          <span class="rounded-lg bg-brand-50 text-brand-700 px-3 py-1.5">Difficulty: ${escapeHtml(o.difficulty) || "n/a"}</span>
          <span class="rounded-lg bg-brand-50 text-brand-700 px-3 py-1.5">Competition: ${escapeHtml(o.competition) || "n/a"}</span>
        </div>
        <div class="mt-4 flex justify-end">
          <button data-choose="${i}" class="rounded-xl border border-brand-500 text-brand-700 hover:bg-brand-50 px-4 py-2 text-sm font-medium">Choose This Idea</button>
        </div>
      </div>`;
    })
    .join("");
}

function recommendationCardHtml(reco) {
  return `<div class="rounded-2xl border-2 border-brand-500 bg-brand-50/40 p-6">
    <div class="text-xs font-semibold uppercase tracking-wide text-brand-700 mb-1">Best Recommendation</div>
    <div class="text-lg font-bold text-slate-900 mb-3">${escapeHtml(reco.best_product)}</div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      ${block("Best niche to use", `<p class="text-sm text-slate-700">${escapeHtml(reco.best_niche) || "&mdash;"}</p>`)}
      ${block("Best product to create", `<p class="text-sm text-slate-700">${escapeHtml(reco.best_product) || "&mdash;"}</p>`)}
      ${block("Best product type", `<p class="text-sm text-slate-700">${escapeHtml(reco.best_product_type || reco.best_format) || "&mdash;"}</p>`)}
      ${block("Suggested title", `<p class="text-sm text-slate-700">${escapeHtml(reco.suggested_title)}</p>`)}
      <div class="md:col-span-2">${block("Why the app selected it", `<p class="text-sm text-slate-700">${escapeHtml(reco.why_selected)}</p>`)}</div>
      <div class="md:col-span-2">${block("Suggested next step", `<p class="text-sm font-medium text-slate-800">${escapeHtml(reco.next_step)}</p>`)}</div>
    </div>
    <div class="mt-5 flex justify-end">
      <button id="buildBtn" class="btn-primary">Use Best Recommendation</button>
    </div>
  </div>`;
}

// Wire the Choose This Idea / Use Best Recommendation buttons inside a container.
// `d` must be a discovery-shaped object ({opportunities, recommendation, mode}); it
// is set as lastDiscovery so chooseIdea/buildRecommended/saveResearchOnly all work.
function wireOpportunityButtons(scopeEl, d) {
  lastDiscovery = d;
  d._outEl = scopeEl; // where chooseIdea renders the confirmation / re-renders cards
  const ops = d.opportunities || [];
  scopeEl.querySelectorAll("[data-choose]").forEach((b) => {
    b.onclick = () => chooseIdea(ops[Number(b.dataset.choose)]);
  });
  const build = scopeEl.querySelector("#buildBtn");
  if (build) build.onclick = buildRecommended;
  const saveBtn = scopeEl.querySelector("#saveResearchBtn");
  if (saveBtn) saveBtn.onclick = saveResearchOnly;
}

function renderDiscovery(d) {
  const out = document.getElementById("marketOutput");
  const ops = d.opportunities || [];
  const reco = d.recommendation || {};

  if (!ops.length) {
    lastDiscovery = d;
    out.innerHTML = card('<p class="text-sm text-slate-500">No opportunities were returned. Try again or add a broad interest area.</p>');
    return;
  }

  out.innerHTML = `<div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h3 class="text-base font-bold text-slate-900">Recommended Product Opportunities</h3>
      <div class="flex items-center gap-3">
        ${modeBadgeHtml(d.mode)}
        <button id="saveResearchBtn" class="rounded-xl border border-slate-300 text-slate-600 hover:bg-slate-50 px-3 py-1.5 text-sm font-medium">Save Research Only</button>
      </div>
    </div>
    <p class="text-sm text-slate-500">Pick an opportunity with <span class="font-medium text-slate-700">Choose This Idea</span>, or jump to the strongest with <span class="font-medium text-slate-700">Use Best Recommendation</span> to start planning your product.</p>
    <div class="space-y-4">${opportunityCardsHtml(ops)}</div>
    ${recommendationCardHtml(reco)}
  </div>`;

  d._rerender = () => renderDiscovery(d);
  wireOpportunityButtons(out, d);
}

async function saveResearchOnly() {
  const d = lastDiscovery;
  if (!d) return;
  const reco = d.recommendation || {};
  const subject = reco.best_niche || d.niche || d.interest || (d.opportunities && d.opportunities[0] && d.opportunities[0].niche) || "Market research";
  try {
    await api("/projects", {
      method: "POST",
      body: JSON.stringify({ name: `Research: ${subject}`, type: "research_plan", data: d }),
    });
    toast("Research saved. Choose an idea anytime to start planning.");
    loadProjects();
  } catch (e) {
    toast(e.message, "error");
  }
}

function buildRecommended() {
  const d = lastDiscovery;
  if (!d) return;
  const ops = d.opportunities || [];
  const reco = d.recommendation || {};
  const op = ops.find((o) => o.product_idea === reco.best_product) || ops[0];
  if (!op) return toast("Nothing to build yet", "error");
  chooseIdea(op);
}

function opportunityToProjectData(op) {
  const reco = (lastDiscovery && lastDiscovery.recommendation) || {};
  return {
    niche: op.niche || op.product_idea,
    audience: op.target_audience,
    product_type: op.product_type,
    mode: (lastDiscovery && lastDiscovery.mode) || "ai_estimated",
    report: {
      niche_summary: op.why_opportunity,
      target_audience: op.target_audience,
      customer_problems: op.customer_problem ? [op.customer_problem] : [],
      search_terms: [],
      product_ideas: [op.product_idea],
      best_format: op.product_type,
      title_ideas: reco.suggested_title ? [reco.suggested_title] : [],
      price_range: op.price_range,
      difficulty: op.difficulty,
      competition: op.competition,
      opportunity_score: op.opportunity_score,
      why_worth_creating: op.why_opportunity,
      next_step: reco.next_step || "",
    },
    opportunity: op,
  };
}

function selectionOutEl() {
  return (lastDiscovery && lastDiscovery._outEl) || document.getElementById("marketOutput");
}

function opportunityToPlanForm(op) {
  return {
    idea: op.product_idea || op.niche || "",
    product_type: op.product_type || "",
    audience: op.target_audience || "",
    problem: op.customer_problem || "",
    outcome: "",
    tone: "",
    length: "",
    difficulty: op.difficulty || "",
    notes: [op.why_opportunity, op.sales_angle].filter(Boolean).join(" "),
  };
}

// Automatic path: choosing an opportunity (or the best recommendation) generates
// the product plan in the background and shows a confirmation screen. It NEVER
// opens the Product Planning form — that is reserved for the manual path and the
// "Edit Plan" button. The plan is saved to ONE record (reused, never duplicated).
async function chooseIdea(op) {
  if (!op) return;
  const out = selectionOutEl();
  const reco = (lastDiscovery && lastDiscovery.recommendation) || {};
  const whySelected = reco.why_selected || op.why_opportunity || "";
  out.innerHTML = spinner("Creating your product plan...");
  try {
    const planData = await api("/generate-product-plan", {
      method: "POST",
      body: JSON.stringify({ form: opportunityToPlanForm(op) }),
    });
    const research = opportunityToProjectData(op);
    const payload = {
      ...planData,
      niche: research.niche,
      audience: research.audience,
      mode: research.mode,
      report: research.report,
      opportunity: op,
      why_selected: whySelected,
      stage: "product_plan_saved",
    };
    const name = (planData.plan && planData.plan.product_title) || op.product_idea || "Untitled Product Plan";
    const targetId = lastDiscovery && lastDiscovery._source_project_id != null ? lastDiscovery._source_project_id : null;
    markUserSaved(payload);
    const saved = targetId != null
      ? await api(`/projects/${targetId}`, { method: "PUT", body: JSON.stringify({ name, type: "product_plan", data: payload }) })
      : await api("/save-product-plan", { method: "POST", body: JSON.stringify({ name, data: payload }) });
    if (saved && saved.id != null) {
      payload._project_id = saved.id;
      if (lastDiscovery) lastDiscovery._source_project_id = saved.id;
    }
    loadProjects();
    renderBestSelected(payload, whySelected, op);
  } catch (e) {
    out.innerHTML = card(
      `<p class="text-rose-600 text-sm mb-3">${escapeHtml(e.message)}</p>
       <button id="backToOpps" class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">Back to opportunities</button>`
    );
    const back = out.querySelector("#backToOpps");
    if (back) back.onclick = () => { if (lastDiscovery && lastDiscovery._rerender) lastDiscovery._rerender(); };
  }
}

function selRow(label, value, strong) {
  return `<div>
    <h4 class="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">${label}</h4>
    <p class="text-sm ${strong ? "font-semibold text-slate-900" : "text-slate-700"}">${escapeHtml(value) || '<span class="text-slate-400">n/a</span>'}</p>
  </div>`;
}

function renderBestSelected(planData, whySelected, op) {
  const out = selectionOutEl();
  const p = planData.plan || {};
  out.innerHTML = `<div class="rounded-2xl border-2 border-emerald-500 bg-emerald-50/40 p-6">
    <span class="inline-flex items-center rounded-full bg-emerald-600 text-white text-xs font-semibold px-3 py-1">Best Product Selected</span>
    <div class="text-xl font-bold text-slate-900 mt-3 mb-1">${escapeHtml(p.product_title) || escapeHtml(op.product_idea)}</div>
    <div class="text-sm text-slate-500 mb-5">Your product plan is ready. Build it now, fine-tune it, or pick a different idea.</div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      ${selRow("Product type", p.product_type || op.product_type)}
      ${selRow("Suggested price range", p.price_range || op.price_range)}
      ${selRow("Target audience", p.target_audience || op.target_audience)}
      ${selRow("Main customer problem", p.customer_problem || op.customer_problem)}
      <div class="md:col-span-2">${selRow("Product promise", p.product_promise, true)}</div>
      <div class="md:col-span-2">${selRow("Recommended sales angle", p.sales_angle || op.sales_angle)}</div>
      <div class="md:col-span-2">${selRow("Why the app selected this product", whySelected)}</div>
    </div>
    <div class="mt-6 flex flex-wrap gap-3 justify-end">
      <button id="selChooseOther" class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">Choose Different Idea</button>
      <button id="selSavePlan" class="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50">Save Plan</button>
      <button id="selEditPlan" class="rounded-xl border border-brand-500 text-brand-700 hover:bg-brand-50 px-4 py-2 text-sm font-medium">Edit Plan</button>
      <button id="selBuild" class="btn-primary">Build Product</button>
    </div>
  </div>`;
  out.querySelector("#selBuild").onclick = () => sendToBuilder(planData);
  out.querySelector("#selEditPlan").onclick = () => editPlanFromSelection(planData, op);
  out.querySelector("#selSavePlan").onclick = () => confirmSavePlan(planData);
  out.querySelector("#selChooseOther").onclick = () => {
    if (lastDiscovery && lastDiscovery._rerender) lastDiscovery._rerender();
  };
}

// Re-saves the current plan record and toasts a visible confirmation so the user
// knows the research is durably stored. Safe to call multiple times — uses the
// same project_id so it's an in-place update, not a duplicate.
async function confirmSavePlan(planData) {
  if (!planData) return;
  const name = (planData.plan && planData.plan.product_title) || "Untitled Product Plan";
  const targetId = planData._project_id != null ? planData._project_id : null;
  const { _project_id, ...rest } = planData;
  const payload = { ...rest, stage: "product_plan_saved" };
  try {
    markUserSaved(payload);
    const saved = targetId != null
      ? await api(`/projects/${targetId}`, { method: "PUT", body: JSON.stringify({ name, type: "product_plan", data: payload }) })
      : await api("/save-product-plan", { method: "POST", body: JSON.stringify({ name, data: payload }) });
    if (saved && saved.id != null) planData._project_id = saved.id;
    loadProjects();
    toast(`Plan saved (project #${planData._project_id}). Open it from Saved Projects anytime.`);
  } catch (e) {
    toast(e.message, "error");
  }
}

function briefRow(label, value) {
  const v = (value == null || value === "") ? '<span class="text-slate-400">n/a</span>' : escapeHtml(value);
  return `<div>
    <h4 class="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">${escapeHtml(label)}</h4>
    <p class="text-sm text-slate-700">${v}</p>
  </div>`;
}

// Render the researched product brief inside the Ebook Builder view. The brief
// is the saved project data: plan (product_title, audience, tone, ...), opportunity
// (customer_problem, sales_angle, why_opportunity, ...), and recommendation
// (suggested_title, next_step, why_selected).
function renderBriefPanel(d) {
  const panel = document.getElementById("ebookBriefPanel");
  if (!panel) return;
  if (!d) { panel.classList.add("hidden"); panel.innerHTML = ""; return; }
  const plan = d.plan || {};
  const op = d.opportunity || {};
  const reco = d.recommendation || {};
  const summary = plan.research_summary || op.why_opportunity || reco.why_selected || "";
  const chapterDir = plan.chapter_direction || reco.next_step || "";
  panel.classList.remove("hidden");
  panel.innerHTML = `<div class="rounded-2xl border-2 border-emerald-500 bg-emerald-50/40 p-5">
    <div class="flex items-center justify-between mb-3">
      <span class="inline-flex items-center rounded-full bg-emerald-600 text-white text-xs font-semibold px-3 py-1">Researched Plan Attached</span>
      <div class="flex items-center gap-3">
        <span class="text-xs text-slate-500">Project #${d._project_id != null ? d._project_id : "?"}</span>
        <button id="ebookBriefClear" type="button" class="text-xs text-slate-500 hover:text-slate-800 underline">Clear research</button>
      </div>
    </div>
    <div class="text-lg font-bold text-slate-900">${escapeHtml(plan.product_title || op.product_idea || "Untitled")}</div>
    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
      ${briefRow("Target audience", plan.target_audience || op.target_audience)}
      ${briefRow("Customer problem", plan.customer_problem || op.customer_problem)}
      ${briefRow("Product promise", plan.product_promise)}
      ${briefRow("Sales angle", plan.sales_angle || op.sales_angle)}
      ${briefRow("Suggested title", reco.suggested_title || plan.product_title)}
      ${briefRow("Tone", plan.tone)}
      ${briefRow("User goal", d.user_goal || plan.user_goal)}
      ${briefRow("Chapter direction", chapterDir)}
    </div>
    ${summary ? `<details class="mt-3 text-sm" open>
      <summary class="cursor-pointer text-slate-700 font-medium">Research summary</summary>
      <div class="mt-2 text-slate-700 whitespace-pre-line">${escapeHtml(summary)}</div>
    </details>` : ""}
  </div>`;
  const clear = panel.querySelector("#ebookBriefClear");
  if (clear) clear.onclick = () => {
    pendingEbookBrief = null;
    renderBriefPanel(null);
    toast("Research cleared. The ebook will be drafted from the topic only.");
  };
}

// "Edit Plan" is the ONLY automatic-path route into the Product Planning form.
// It carries the saved plan's id so re-generating updates the same record.
async function editPlanFromSelection(planData, op) {
  const p = planData.plan || {};
  go("planning");
  await loadPlanSources();
  planLineageId = planData._project_id != null ? planData._project_id : null;
  document.getElementById("planSource").value = "";
  setPlanField("idea", p.product_title || op.product_idea || "");
  setPlanProductType(p.product_type || op.product_type);
  setPlanField("audience", p.target_audience || op.target_audience || "");
  setPlanField("problem", p.customer_problem || op.customer_problem || "");
  setPlanField("outcome", p.main_transformation || p.product_promise || "");
  setPlanField("notes", p.sales_angle || op.why_opportunity || "");
  toast("Edit the details, then click Generate Product Plan to update it.");
}

async function runDiscover() {
  const interest = document.getElementById("findInterest").value.trim();
  const audience = document.getElementById("findAudience").value.trim();
  const product_type = document.getElementById("findProductType").value;
  const difficulty = document.getElementById("findDifficulty").value;
  const goal = document.getElementById("findGoal").value.trim();
  const out = document.getElementById("marketOutput");
  out.innerHTML = spinner("Researching the best products for you...");
  setBusy("findBtn", true);
  try {
    const data = await api("/discover-products", {
      method: "POST",
      body: JSON.stringify({ interest, audience, product_type, difficulty, goal }),
    });
    renderDiscovery(data);
  } catch (e) {
    out.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusy("findBtn", false);
  }
}

// ---------- product planning ----------
let planResearchCache = [];
// When an automatic-path plan is sent to "Edit Plan", this carries the existing
// product_plan record id so re-generating updates it in place (no duplicate).
let planLineageId = null;

function initPlanTypes() {
  const sel = document.getElementById("planProductType");
  if (sel && !sel.options.length) {
    sel.innerHTML = MARKET_PRODUCT_TYPES.map((t) => `<option value="${escapeHtml(t)}">${escapeHtml(t)}</option>`).join("");
  }
}

async function loadPlanSources() {
  const sel = document.getElementById("planSource");
  if (!sel) return;
  let projects = [];
  try { projects = await api("/projects"); } catch (e) { /* ignore */ }
  planResearchCache = projects.filter((p) => p.type === "research_plan");
  sel.innerHTML =
    '<option value="">Enter manually</option>' +
    planResearchCache
      .map((p) => `<option value="${p.id}">${escapeHtml(p.name)}</option>`)
      .join("");
}

function setPlanField(name, value) {
  const el = document.getElementById("planForm").elements[name];
  if (el) el.value = value || "";
}

function setPlanProductType(pt) {
  const match = MARKET_PRODUCT_TYPES.find((t) => t.toLowerCase() === String(pt || "").toLowerCase());
  setPlanField("product_type", match || "Not Sure Yet");
}

function prefillPlanFromResearch(project) {
  if (!project) return;
  const d = project.data || {};
  const r = d.report || {};
  const idea = (r.product_ideas && r.product_ideas[0]) || d.niche || "";
  setPlanField("idea", idea);
  const pt = d.product_type && d.product_type !== "Not Sure Yet" ? d.product_type : (r.best_format || "Not Sure Yet");
  setPlanProductType(pt);
  setPlanField("audience", r.target_audience || d.audience || "");
  setPlanField("problem", (r.customer_problems && r.customer_problems[0]) || "");
  setPlanField("notes", r.why_worth_creating || "");
}

function clearPlanForm() {
  document.getElementById("planForm").reset();
  initPlanTypes();
  document.getElementById("planSource").value = "";
  document.getElementById("planOutput").innerHTML = "";
  planLineageId = null;
}

function planRow(label, value) {
  return `<div>
    <h4 class="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">${label}</h4>
    <p class="text-sm text-slate-700">${escapeHtml(value) || '<span class="text-slate-400">n/a</span>'}</p>
  </div>`;
}

function renderPlan(d) {
  const out = document.getElementById("planOutput");
  const p = d.plan || {};
  const outline = (p.outline || []).length
    ? `<ol class="list-decimal ml-5 space-y-1 text-sm text-slate-700">${p.outline.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ol>`
    : '<p class="text-sm text-slate-400">None</p>';
  const bonuses = (p.bonus_ideas || []).length
    ? `<ul class="list-disc ml-5 space-y-1 text-sm text-slate-700">${p.bonus_ideas.map((i) => `<li>${escapeHtml(i)}</li>`).join("")}</ul>`
    : '<p class="text-sm text-slate-400">None</p>';

  out.innerHTML = card(`
    <div class="mb-5">
      <div class="text-xs font-medium text-slate-500">Product blueprint</div>
      <div class="text-lg font-bold text-slate-900">${escapeHtml(p.product_title)}</div>
      <div class="text-sm text-slate-500">${escapeHtml(p.subtitle)}</div>
      <div class="mt-2 flex flex-wrap gap-2 text-xs">
        <span class="rounded-lg bg-brand-50 text-brand-700 px-3 py-1.5">${escapeHtml(p.product_type) || "Product"}</span>
        <span class="rounded-lg bg-brand-50 text-brand-700 px-3 py-1.5">Price: ${escapeHtml(p.price_range) || "n/a"}</span>
      </div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
      ${planRow("Target audience", p.target_audience)}
      ${planRow("Customer problem", p.customer_problem)}
      ${planRow("Product promise", p.product_promise)}
      ${planRow("Main transformation", p.main_transformation)}
      <div class="md:col-span-2">${planRow("Product description", p.product_description)}</div>
      <div class="md:col-span-2">
        <h4 class="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">Chapter / section outline</h4>${outline}
      </div>
      <div class="md:col-span-2">
        <h4 class="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">Bonus ideas</h4>${bonuses}
      </div>
      ${planRow("Cover concept", p.cover_concept)}
      ${planRow("Sales angle", p.sales_angle)}
      <div class="md:col-span-2">${planRow("Marketing hook", p.marketing_hook)}</div>
      <div class="md:col-span-2">${planRow("Recommended next step", p.next_step)}</div>
    </div>
  `);

  const bar = document.createElement("div");
  bar.className = "flex justify-end";
  const btn = document.createElement("button");
  btn.className = "btn-primary";
  btn.textContent = "Send to Product Factory";
  btn.onclick = () => sendToBuilder(d);
  bar.appendChild(btn);
  out.appendChild(bar);
}

function factoryTypeIdFromPlan(plan) {
  const res = resolveFactoryTypeFromPlan(plan);
  return (res && res.factoryId) || null;
}

// Resolve a product_plan to either an active factory type, a hidden
// factory type (which must not be unhide-routed), or unknown.
//
// Returned shape:
//   { status: "active",  factoryId: "ebook" }                       // safe to navigate
//   { status: "hidden",  factoryId: "planner", hiddenReason: "..." } // blocked, keep plan saved
//   { status: "unknown" }                                            // no confident match
//
// This replaces the old factoryTypeIdFromPlan() which only knew about
// active builders. When a product plan names a hidden builder (e.g.
// "Printable and fillable digital planning kit" → planner), the handoff
// shows a clear blocked message instead of silently dropping the user
// in the wrong builder.
function resolveFactoryTypeFromPlan(plan) {
  const pt = String((plan && plan.product_type) || "").toLowerCase().trim();
  if (!pt) return { status: "unknown" };

  // 1. Exact label match against the canonical Product Factory types.
  const byLabel = PRODUCT_TYPES.find((t) => t.label.toLowerCase() === pt);
  if (byLabel) {
    if (byLabel.hidden) {
      return { status: "hidden", factoryId: byLabel.id, hiddenReason: hiddenReasonFor(byLabel.id) };
    }
    return { status: "active", factoryId: byLabel.id };
  }
  // 2. Exact id match.
  const byId = PRODUCT_TYPES.find((t) => t.id === pt);
  if (byId) {
    if (byId.hidden) {
      return { status: "hidden", factoryId: byId.id, hiddenReason: hiddenReasonFor(byId.id) };
    }
    return { status: "active", factoryId: byId.id };
  }

  // 3. Heuristic detection for active builders.
  if (pt.includes("color")) return { status: "active", factoryId: "coloring_book" };
  if (pt.includes("word search")) return { status: "active", factoryId: "word_search" };
  if (pt.includes("crossword")) return { status: "active", factoryId: "crossword" };
  if (pt.includes("math") || (pt.includes("worksheet") && !pt.includes("spelling"))) {
    return { status: "active", factoryId: "math_worksheet" };
  }

  // 4. Heuristic detection for hidden builders.
  if (pt.includes("spelling")) {
    return {
      status: "hidden",
      factoryId: "spelling_worksheet",
      hiddenReason: hiddenReasonFor("spelling_worksheet"),
    };
  }
  if (pt.includes("flip")) return { status: "hidden", factoryId: "flip_book", hiddenReason: hiddenReasonFor("flip_book") };
  if (pt.includes("cover")) return { status: "hidden", factoryId: "cover_design", hiddenReason: hiddenReasonFor("cover_design") };
  if (pt.includes("marketing") || pt.includes("sales copy") || pt.includes("ad script")) {
    return { status: "hidden", factoryId: "marketing_kit", hiddenReason: hiddenReasonFor("marketing_kit") };
  }
  if (
    pt.includes("planner") ||
    pt.includes("planning") ||
    pt.includes("printable") ||
    pt.includes("fillable") ||
    /\bkit\b/.test(pt) ||
    pt.includes("routine") ||
    pt.includes("schedule") ||
    pt.includes("tracker") ||
    pt.includes("weekly kit")
  ) {
    return { status: "hidden", factoryId: "planner", hiddenReason: hiddenReasonFor("planner") };
  }

  // 5. Default active catch-all: book/guide/workbook/checklist → ebook.
  if (pt.includes("book") || pt.includes("guide") || pt.includes("workbook") || pt.includes("checklist")) {
    return { status: "active", factoryId: "ebook" };
  }
  return { status: "unknown" };
}

function hiddenReasonFor(factoryId) {
  const subject =
    factoryId === "planner" ? "Planner products" :
    factoryId === "cover_design" ? "Cover Design" :
    factoryId === "flip_book" ? "Flip Book" :
    factoryId === "marketing_kit" ? "Marketing Kit" :
    factoryId === "spelling_worksheet" ? "Spelling Worksheet" :
    "This product type";
  const verb = subject.endsWith("products") ? "are" : "is";
  return (
    subject + " " + verb + " not ready in the public builder yet. " +
    "This plan has been saved as a blueprint and is available in Saved Projects. " +
    "Pick an active product type in the Product Factory when it's ready, or regenerate the plan with a different product type."
  );
}

function prefillFactoryFromPlan(plan) {
  const id = factoryTypeIdFromPlan(plan);
  if (!id) return false;
  selectFactoryType(id);
  const form = document.getElementById("factoryForm");
  const title = plan.product_title || "";
  const audience = plan.target_audience || "";
  const map = {
    topic: title,
    theme: title,
    title: title,
    worksheet_title: title,
    book_title: title,
    subtitle: plan.subtitle || "",
    audience: audience,
    age_group: audience,
    product_type: plan.product_type || "",
    cta: plan.marketing_hook || "",
    image_concept: plan.cover_concept || "",
    customer_problem: plan.customer_problem || "",
    product_promise: plan.product_promise || "",
    main_transformation: plan.main_transformation || "",
  };
  Object.entries(map).forEach(([k, v]) => {
    const el = form.elements[k];
    if (el && v) el.value = v;
  });
  return true;
}

async function sendToBuilder(d) {
  const plan = d.plan || {};
  const name = plan.product_title || "Untitled Product Plan";
  const targetId = d._project_id != null ? d._project_id : null;
  const { _project_id, ...rest } = d;
  const payload = { ...rest, stage: "product_plan_saved" };

  // Always save the blueprint first. Even if the handoff can't find an
  // active builder, the plan must be persisted so the user can come back
  // to it from Saved Projects.
  let saved;
  try {
    markUserSaved(payload);
    saved = targetId != null
      ? await api(`/projects/${targetId}`, { method: "PUT", body: JSON.stringify({ name, type: "product_plan", data: payload }) })
      : await api("/save-product-plan", { method: "POST", body: JSON.stringify({ name, data: payload }) });
    if (saved && saved.id != null) d._project_id = saved.id;
    loadProjects();
  } catch (e) {
    toast("Could not save blueprint: " + e.message, "error");
    return;
  }

  const resolution = resolveFactoryTypeFromPlan(plan);

  // Hidden product type (planner, cover_design, marketing_kit, flip_book):
  // the matching builder is intentionally hidden from the public picker
  // (see PUBLIC_FACTORY_MENU_CLEANUP_LOCK.md). Do NOT unhide or silently
  // route — show a clear blocked message and keep the saved plan.
  if (resolution.status === "hidden") {
    toast(
      resolution.hiddenReason ||
      "This product type is not ready in the public builder yet. This plan has been saved as a blueprint.",
      "error"
    );
    return;
  }

  // Active Ebook: open the dedicated Ebook Builder view with the researched
  // brief attached, pre-fill the source input, and AUTO-FIRE the build. The
  // "Build Product" / "Send to Product Builder" click is the user saying
  // "build it" — they shouldn't have to click a second button to actually
  // generate. The post-save Next Steps panel (Download PDF / ZIP / Selling)
  // appears automatically when the build finishes.
  if (resolution.status === "active" && resolution.factoryId === "ebook") {
    pendingEbookBrief = d;
    go("ebook");
    document.getElementById("ebookInput").value = plan.product_title || "";
    renderBriefPanel(d);
    toast("Building your ebook from the research...");
    // Auto-fire the build. runEbook() reads the source from #ebookInput
    // (just set above) and POSTs to /generate-ebook with the attached
    // pendingEbookBrief as the contract. The async /generate-ebook call
    // (which can take 30+ seconds for a full ebook) is the user-perceived
    // "build" — the spinner in #ebookOutput keeps them oriented.
    runEbook();
    return;
  }

  // Active other (coloring_book, word_search, crossword, math_worksheet,
  // spelling_worksheet): route to the Product Factory and prefill the form.
  go("factory");
  if (d._project_id != null) pendingProductProjectId = d._project_id; // carry lineage to the product step
  const ok = prefillFactoryFromPlan(plan);
  if (ok) {
    toast("Saved and sent to the Product Factory with your plan prefilled.");
  } else if (resolution.status === "unknown") {
    toast("Saved. The plan is in Saved Projects — pick a product type in the Product Factory to continue.");
  } else {
    toast("Saved. Pick a product type in the Product Factory to continue.");
  }
}

async function runPlan() {
  const form = document.getElementById("planForm");
  const fields = {};
  new FormData(form).forEach((v, k) => { fields[k] = v; });
  if (!(fields.idea || "").trim()) return toast("Enter a product idea", "error");

  const out = document.getElementById("planOutput");
  out.innerHTML = spinner("Building your product blueprint...");
  setBusy("planBtn", true);
  try {
    // Lineage is derived from the selected research source so the plan morphs
    // that exact record in place (no duplicate). Manual entry (no source) = new record.
    const srcSel = document.getElementById("planSource");
    const srcId = srcSel && srcSel.value ? Number(srcSel.value) : planLineageId;
    const data = await api("/generate-product-plan", { method: "POST", body: JSON.stringify({ form: fields }) });
    if (srcId != null) data._project_id = srcId;
    renderPlan(data);
  } catch (e) {
    out.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusy("planBtn", false);
  }
}

// ---------- product factory ----------
function buildFactoryTypes() {
  const wrap = document.getElementById("factoryTypes");
  if (!wrap) return;
  wrap.innerHTML = "";
  // Hidden types are kept in the catalog (so saved-project re-opens still work
  // and direct API calls get a clear error from the backend), but they do
  // not appear in the public picker. See HIDDEN_PRODUCT_TYPES in app.py.
  PRODUCT_TYPES.filter((t) => !t.hidden).forEach((t) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "group flex flex-col items-start gap-2 rounded-xl border px-4 py-3 text-left transition " +
      (factoryType === t.id
        ? "border-brand-500 bg-brand-50 ring-2 ring-brand-200"
        : "border-slate-200 hover:border-brand-300 hover:bg-brand-50/40");
    btn.dataset.ft = t.id;
    btn.innerHTML = `
      <span class="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-100 text-brand-700">
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="${t.icon}"/></svg>
      </span>
      <span class="text-sm font-semibold text-slate-800">${t.label}</span>
      <span class="text-xs text-slate-500">${t.desc}</span>`;
    btn.onclick = () => selectFactoryType(t.id);
    wrap.appendChild(btn);
  });
}

function fieldControl(f) {
  const base =
    'class="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-200 outline-none"';
  const ac = f.autocomplete === "off" ? ' autocomplete="off"' : "";
  const ph = f.placeholder ? ` placeholder="${escapeHtml(f.placeholder)}"` : "";
  if (f.type === "textarea") {
    return `<textarea name="${f.name}" rows="3" ${base}${ac}${ph}></textarea>`;
  }
  if (f.type === "select") {
    const opts = f.options.map((o) => {
      const value = typeof o === "object" && o ? o.value : o;
      const label = typeof o === "object" && o ? (o.label || o.value) : o;
      const sel = f.default === value || f.default === label ? " selected" : "";
      return `<option value="${escapeHtml(value)}"${sel}>${escapeHtml(label)}</option>`;
    }).join("");
    return `<select name="${f.name}" ${base}${ac}>${opts}</select>`;
  }
  const type = f.type === "number" ? "number" : "text";
  const val = f.value != null ? ` value="${escapeHtml(f.value)}"` : "";
  return `<input type="${type}" name="${f.name}"${val} ${base}${ac}${ph} />`;
}

function selectFactoryType(id) {
  factoryType = id;
  const t = productType(id);
  buildFactoryTypes();
  document.getElementById("factoryFormTitle").textContent = `Create your ${t.label}`;
  const form = document.getElementById("factoryForm");
  const guide = t.guide
    ? `<div class="sm:col-span-2 rounded-xl border border-brand-200 bg-brand-50 px-4 py-3 text-sm text-slate-700">
         <p class="font-semibold text-brand-800 mb-1">How this works</p>
         <p>${escapeHtml(t.guide)}</p>
       </div>`
    : "";
  form.innerHTML =
    guide +
    t.fields
      .map((f) => {
        const span = f.type === "textarea" ? "sm:col-span-2" : "";
        const req = f.required ? ' <span class="text-rose-500">*</span>' : "";
        const hint = f.hint
          ? `<p class="mt-1 text-xs text-slate-500">${escapeHtml(f.hint)}</p>`
          : "";
        return `<div class="${span}">
        <label class="block text-xs font-medium text-slate-600 mb-1">${f.label}${req}</label>
        ${fieldControl(f)}
        ${hint}
      </div>`;
      })
      .join("");
  document.getElementById("factoryFormWrap").classList.remove("hidden");
  document.getElementById("factoryOutput").innerHTML = "";

  // ── COLORING BOOK: auto-manage pages field for Single Sheet ──────────────
  if (id === "coloring_book") {
    _coloringBookSetupForm();
  }

  // ── CROSSWORD: Full Book is locked to 12 puzzles (25-page book) ───────────
  if (id === "crossword") {
    _crosswordSetupForm();
  }

  // Scroll form into view so beginners see the next step immediately.
  const wrap = document.getElementById("factoryFormWrap");
  if (wrap && typeof wrap.scrollIntoView === "function") {
    wrap.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function _crosswordSetupForm() {
  const form = document.getElementById("factoryForm");
  if (!form) return;
  const outputEl = form.elements["output_format"];
  const puzzlesEl = form.elements["puzzles"];

  function enforceFullBookCount() {
    if (!puzzlesEl || !outputEl) return;
    const isBook = String(outputEl.value || "").toLowerCase().includes("book");
    if (isBook) {
      puzzlesEl.value = "12";
      puzzlesEl.readOnly = true;
      puzzlesEl.style.opacity = "0.85";
      puzzlesEl.style.cursor = "not-allowed";
    } else {
      puzzlesEl.value = "1";
      puzzlesEl.readOnly = true;
      puzzlesEl.style.opacity = "0.85";
      puzzlesEl.style.cursor = "not-allowed";
    }
  }

  enforceFullBookCount();
  if (outputEl) outputEl.onchange = enforceFullBookCount;
}

// Keep Single Sheet pages locked to 1 and in sync with output_format.
// Called both on factory-type change and after restoring saved-project fields.
function _coloringBookSetupForm() {
  const form = document.getElementById("factoryForm");
  if (!form) return;
  const outputEl = form.elements["output_format"];
  const pagesEl = form.elements["pages"];

  function enforceSingleSheet(sheetSelected) {
    if (!pagesEl) return;
    if (sheetSelected) {
      pagesEl.value = "1";
      pagesEl.readOnly = true;
      pagesEl.style.opacity = "0.5";
      pagesEl.style.cursor = "not-allowed";
    } else {
      // Digital Book: allow editing; restore to sensible default if still at 1
      pagesEl.readOnly = false;
      pagesEl.style.opacity = "1";
      pagesEl.style.cursor = "";
      if (pagesEl.value === "1") pagesEl.value = "12";
    }
  }

  // Run once on init (handles saved-project restore)
  enforceSingleSheet(outputEl && outputEl.value === "Single Sheet");

  // Watch future changes
  if (outputEl) {
    outputEl.onchange = () => enforceSingleSheet(outputEl.value === "Single Sheet");
  }
}

function resetFactory() {
  factoryType = null;
  buildFactoryTypes();
  document.getElementById("factoryFormWrap").classList.add("hidden");
  document.getElementById("factoryOutput").innerHTML = "";
}

function collectFactoryFields() {
  const form = document.getElementById("factoryForm");
  const fields = {};
  new FormData(form).forEach((v, k) => { fields[k] = v; });
  // Crossword Full Book is always 12 puzzles (25 pages). Enforce on submit so
  // browser autofill / stale restored values (e.g. "10") cannot thin the book.
  if (factoryType === "crossword") {
    const fmt = String(fields.output_format || "").toLowerCase();
    if (fmt.includes("book")) {
      fields.output_format = "Full Book";
      fields.puzzles = "12";
    } else {
      fields.puzzles = "1";
    }
  }
  return fields;
}

async function _runColoringBookStage(d, nextStage, approvals) {
  const fields = collectFactoryFields();
  fields.package_id = d.package_id || (d.fields && d.fields.package_id) || "";
  fields.generation_stage = nextStage;
  fields.character_approved = approvals.character_approved ? "true" : "false";
  fields.sample_approved = approvals.sample_approved ? "true" : "false";
  if (approvals.force_image_regen) fields.force_image_regen = "true";
  if (d.cover_image_path) fields.reference_image_path = d.cover_image_path;
  const out = document.getElementById("factoryOutput");
  const paidNote =
    nextStage === "full"
      ? "Step 3 of 3 — finishing your coloring book (uses AI image credits)…"
      : nextStage === "sample_interior"
        ? "Step 2 of 3 — creating one sample page to approve (uses AI image credits)…"
        : "Step 1 of 3 — creating your cover preview (uses AI image credits)…";
  out.innerHTML = spinner(paidNote);
  setBusy("factoryBtn", true);
  try {
    const data = await api("/generate-product", {
      method: "POST",
      body: JSON.stringify({ product_type: "coloring_book", fields }),
    });
    data.stage = "product_generated";
    if (d._project_id != null) data._project_id = d._project_id;
    renderProduct(data);
    scrollNextStepsPanelIntoView(data);
  } catch (e) {
    out.innerHTML = card(
      `<p class="text-rose-600 text-sm font-medium mb-2">${escapeHtml(e.message)}</p>
       <p class="text-sm text-slate-600 mb-3">Check your title and theme, then try again. If this keeps happening, switch Artwork quality to “Quick test layout” to verify the form works.</p>
       <button data-cb-retry class="btn-primary">Try again</button>`
    );
    const retry = out.querySelector("[data-cb-retry]");
    if (retry) {
      retry.onclick = () =>
        _runColoringBookStage(d, nextStage, approvals);
    }
  } finally {
    setBusy("factoryBtn", false);
  }
}

function _coloringApprovalStepper(stage) {
  const steps = [
    { id: "cover_preview", label: "1. Cover" },
    { id: "sample_interior", label: "2. Sample page" },
    { id: "full", label: "3. Full book" },
  ];
  const order = { cover_preview: 0, sample_interior: 1, full: 2 };
  const active = order[stage] != null ? order[stage] : 0;
  return `
    <ol class="mb-4 grid grid-cols-3 gap-2">
      ${steps
        .map((s, i) => {
          const state =
            i < active
              ? "border-emerald-300 bg-emerald-50 text-emerald-800"
              : i === active
                ? "border-brand-400 bg-brand-50 text-brand-800 ring-2 ring-brand-200"
                : "border-slate-200 bg-slate-50 text-slate-400";
          return `<li class="rounded-lg border px-2 py-2 text-center text-xs font-semibold ${state}">${s.label}</li>`;
        })
        .join("")}
    </ol>`;
}

function _coloringBookCoverSrc(d) {
  if (d.cover_preview_b64) return `data:image/png;base64,${d.cover_preview_b64}`;
  if (d.package_id) {
    // Prefer composed letter-size cover page when present; fall back to raw art.
    return `/download/${encodeURIComponent(d.package_id)}/cover_page_preview.png`;
  }
  return "";
}

function _coloringBookFullCoverPreviewHtml(d, { caption } = {}) {
  const src = _coloringBookCoverSrc(d);
  const label = caption || "Full-size cover preview (one US Letter page)";
  if (!src) {
    return `<p class="text-sm text-slate-500">Cover preview image not available yet.</p>`;
  }
  // Letter aspect, large in the factory preview — not a comic-strip thumbnail grid.
  return `
    <div class="mb-2">
      <p class="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">${escapeHtml(label)}</p>
      <div class="mx-auto w-full max-w-2xl rounded-lg border border-slate-200 bg-slate-100 shadow-md overflow-hidden" style="aspect-ratio: 8.5 / 11;">
        <img alt="Full-size coloring book cover" class="block w-full h-full object-contain bg-white"
             src="${src}"
             onerror="if(!this.dataset.fallback){this.dataset.fallback='1';this.src='/download/${encodeURIComponent(d.package_id || '')}/img_cover.png';}" />
      </div>
      <p class="mt-2 text-center text-xs text-slate-500">This is the real book cover at full page size — not a multi-panel comic strip.</p>
    </div>`;
}

function _renderColoringApprovalPanel(d) {
  const stage = d.generation_stage || "cover_preview";
  const bookTitle = String(d.title || d.fields?.coloring_title || "your coloring book").trim();
  const themeHint = String(d.fields?.theme || d.theme || "").trim();
  const warn = d.paid_api_warning
    ? `<div class="mb-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">${escapeHtml(d.paid_api_warning)}</div>`
    : "";
  const coverBlock = _coloringBookFullCoverPreviewHtml(d, {
    caption: "Full-size cover preview",
  });
  const sampleImg = d.sample_preview_b64
    ? `<div class="mx-auto w-full max-w-2xl rounded-lg border border-slate-200 bg-slate-100 shadow-md overflow-hidden" style="aspect-ratio: 8.5 / 11;">
         <img alt="Sample interior page" class="block w-full h-full object-contain bg-white" src="data:image/png;base64,${d.sample_preview_b64}" />
       </div>`
    : "";
  let title = `Step 1 — Approve the cover for “${bookTitle}”`;
  let help =
    "Check that the cover matches your theme, the main character looks right, and the title area feels retail-ready. " +
    "Approving continues to one sample coloring page (uses AI credits).";
  let actions = "";
  if (stage === "cover_preview") {
    actions = `
      <button data-cb-approve-cover class="btn-primary">Looks good — make a sample page</button>
      <button data-cb-regen-cover class="btn-secondary">Try a new cover</button>`;
  } else if (stage === "sample_interior") {
    title = `Step 2 — Approve a sample page for “${bookTitle}”`;
    help =
      "Check the sample coloring page: clear outlines, enough open space to color, and that it matches your theme. " +
      "Approving builds the rest of the book (uses AI credits).";
    actions = `
      <button data-cb-approve-sample class="btn-primary">Looks good — finish the book</button>
      <button data-cb-regen-sample class="btn-secondary">Try a new sample page</button>`;
  }
  const sampleBlock =
    stage === "sample_interior"
      ? `<div class="mt-6"><p class="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">Sample coloring page</p>${sampleImg || '<p class="text-sm text-slate-400">Sample not available yet.</p>'}</div>`
      : "";
  const themeLine = themeHint
    ? `<p class="text-xs text-slate-500 mb-2">Theme: ${escapeHtml(themeHint)}</p>`
    : "";
  return `
    <div class="space-y-4">
      ${_coloringApprovalStepper(stage)}
      <h3 class="text-base font-bold text-slate-900">${escapeHtml(title)}</h3>
      ${themeLine}
      ${warn}
      <p class="text-sm text-slate-600">${escapeHtml(help)}</p>
      ${coverBlock}
      ${sampleBlock}
      <div class="flex flex-wrap gap-2">${actions}</div>
      <p class="text-xs text-slate-400">Tip: approving before the full book keeps quality high and avoids spending credits on pages you don’t want.</p>
    </div>`;
}

function renderProduct(d) {
  // Coloring book staged approval (cover → sample → full). No full paid book until approved.
  if (
    d.product_type === "coloring_book" &&
    (d.needs_approval || d.generation_stage === "cover_preview" || d.generation_stage === "sample_interior")
  ) {
    const out = document.getElementById("factoryOutput");
    out.innerHTML = card(_renderColoringApprovalPanel(d));
    const approveCover = out.querySelector("[data-cb-approve-cover]");
    if (approveCover) {
      approveCover.onclick = () =>
        _runColoringBookStage(d, "sample_interior", {
          character_approved: true,
          sample_approved: false,
        });
    }
    const regenCover = out.querySelector("[data-cb-regen-cover]");
    if (regenCover) {
      regenCover.onclick = () =>
        _runColoringBookStage(d, "cover_preview", {
          character_approved: false,
          sample_approved: false,
          force_image_regen: true,
        });
    }
    const approveSample = out.querySelector("[data-cb-approve-sample]");
    if (approveSample) {
      approveSample.onclick = () => {
        if (
          !window.confirm(
            "Next we’ll finish the rest of your coloring book. This uses AI image credits and can take a few minutes. Continue?"
          )
        ) {
          return;
        }
        _runColoringBookStage(d, "full", {
          character_approved: true,
          sample_approved: true,
        });
      };
    }
    const regenSample = out.querySelector("[data-cb-regen-sample]");
    if (regenSample) {
      regenSample.onclick = () =>
        _runColoringBookStage(d, "sample_interior", {
          character_approved: true,
          sample_approved: false,
          force_image_regen: true,
        });
    }
    return;
  }

  const placementNote = d.word_placement && d.word_placement.note
    ? `<div class="mt-3 mb-2 text-sm text-slate-700 bg-blue-50 border border-blue-200 rounded-lg px-3 py-2">
         <span class="font-semibold text-blue-700">Word placement: </span>${escapeHtml(d.word_placement.note)}
       </div>`
    : "";
  const coloringCoverPreview =
    d.product_type === "coloring_book"
      ? _coloringBookFullCoverPreviewHtml(d)
      : "";
  const out = document.getElementById("factoryOutput");
  out.innerHTML = card(
    // Title row: product type badge + title on the left, "Download PDF" on the
    // right. The button is the prominent "one-click download" for the preview
    // card — same /export-product endpoint as the Next Steps panel's button,
    // but right under the title so the user doesn't have to scroll. The Next
    // Steps panel still has its own Download PDF / ZIP / Open / Back as the
    // canonical post-save action set; this is a convenience entry point.
    `<div class="flex items-center justify-between gap-3 mb-3">
       <div class="flex items-center gap-2 text-xs text-slate-500 min-w-0">
         <span class="rounded-md bg-brand-100 text-brand-700 font-semibold px-2 py-0.5">${escapeHtml(d.product_label || "Product")}</span>
         <span class="truncate">${escapeHtml(d.title || "")}</span>
       </div>
       <button data-preview-dl-pdf class="${NS_BTN}">Download PDF</button>
     </div>${placementNote}${coloringCoverPreview}<div class="prose-out">${md(d.content)}</div>`
  );
  // Wire the preview-card "Download PDF" button. Lazy: only calls /export-product
  // when the user actually clicks, not on render. Reuses d.product_exports if the
  // workflow auto-save or panel probe already fetched it.
  const previewDlBtn = out.querySelector("[data-preview-dl-pdf]");
  if (previewDlBtn) {
    previewDlBtn.onclick = async (e) => {
      const b = e.currentTarget;
      setBusyEl(b, true);
      try {
        // Auto-save so beginners aren't blocked by a hidden "save first" rule.
        if (d._project_id == null) {
          toast("Saving your project so you can download…");
          await ensureProductSaved(d);
          if (typeof d._nsRenderPostSave === "function") d._nsRenderPostSave();
        }
        const projectId = d._project_id;
        if (projectId == null) {
          toast("Could not save the project for download. Use Save Project first.", "error");
          return;
        }
        let ex = (d.exports && d.exports.files) || (d.product_exports && d.product_exports.files);
        if (!ex) {
          const r = await api("/export-product", {
            method: "POST",
            body: JSON.stringify({ project_id: projectId }),
          });
          d.product_exports = r.exports;
          d.export_package_id = r.package_id;
          ex = r.exports && r.exports.files;
        }
        const f = ex && ex.pdf;
        if (f && f.url) {
          await triggerDownload(f.url, f.name || ((d.title || "product") + ".pdf"));
          toast("Your PDF is downloading.");
        } else {
          toast("PDF is not available for this product yet.", "error");
        }
      } catch (err) {
        toast("Could not prepare PDF: " + err.message, "error");
      } finally {
        setBusyEl(b, false);
      }
    };
  }
  // `d` is shared with the Next Steps panel, so enhancement data merged into it
  // later (visuals, exports, packages) is persisted on save. The panel includes
  // Save Project + all post-generation actions and stays as the LAST child so the
  // ebook enhancement section inserts above it.
  out.appendChild(nextStepsPanel(d));

  // Honest QA banner for ebooks that are not export-ready — Download PDF will
  // fail until content / cover issues are fixed (do not pretend it works).
  if (d.product_type === "ebook") {
    const blocked =
      d.quality_blocking ||
      (d.pipeline && Array.isArray(d.pipeline.blocking) && d.pipeline.blocking.length);
    if (blocked) {
      const reasons = (d.pipeline && d.pipeline.blocking) || [
        "Content quality checks must pass before PDF download.",
      ];
      const banner = document.createElement("div");
      banner.className =
        "mt-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900";
      banner.innerHTML =
        `<p class="font-semibold">PDF download is blocked until quality checks pass</p>` +
        `<ul class="mt-2 list-disc pl-5 space-y-1">${reasons
          .map((r) => `<li>${escapeHtml(String(r))}</li>`)
          .join("")}</ul>` +
        `<p class="mt-2 text-amber-800">Revise the manuscript (remove marketing claims like “guaranteed”), finish the cover, then try Download PDF again.</p>`;
      out.insertBefore(banner, out.lastElementChild);
    }
  }

  // ── Edit Cover (crossword / word search / coloring / ebook) ─────────────
  if (
    (d.product_type === "crossword" ||
      d.product_type === "word_search" ||
      d.product_type === "coloring_book" ||
      d.product_type === "ebook") &&
    d._project_id
  ) {
    const coverBtn = document.createElement("button");
    coverBtn.className = "btn-secondary mt-3";
    coverBtn.textContent = "Edit Cover";
    coverBtn.onclick = () => openCoverEditor(d);
    out.appendChild(coverBtn);
  }

  if (d.product_type === "ebook") {
    if (d.preview_html || d.visual_plan) {
      renderEbookEnhancements(out, d); // already-enhanced (e.g. reopened project)
    } else {
      loadEbookEnhancements(out, d);
    }
  }

  // A reopened export-ready / completed project already carries its package, so
  // surface the Download HTML / TXT / ZIP section immediately (no extra click).
  // Gate strictly on persisted export FILES so this never re-runs /export-product
  // (the user-initiated Next Step path handles regeneration when needed).
  const hasExportFiles =
    (d.exports && d.exports.files) || (d.product_exports && d.product_exports.files);
  if (hasExportFiles && d._project_id) {
    nsExport(d);
  }
}

async function loadEbookEnhancements(out, d) {
  const slot = document.createElement("div");
  slot.className = "mt-6";
  slot.innerHTML = card(
    `<div class="flex items-center gap-3 text-sm text-slate-500">
       <span class="inline-block h-4 w-4 rounded-full border-2 border-brand-500 border-t-transparent animate-spin"></span>
       Building visual plan and export package...
     </div>`
  );
  // Insert the loading slot just before the save bar.
  const saveBarEl = out.lastElementChild;
  out.insertBefore(slot, saveBarEl);
  try {
    const enhanced = await api("/enhance-ebook", {
      method: "POST",
      body: JSON.stringify({ title: d.title, content: d.content, fields: d.fields }),
    });
    Object.assign(d, enhanced); // merge so saving persists the full package
    d.stage = "product_generated";
    // If this product is already a saved workflow record, persist the visuals in place.
    if (d._project_id != null) {
      try {
        const { _project_id, ...body } = d;
        await api(`/projects/${_project_id}`, {
          method: "PUT",
          body: JSON.stringify({ name: d.title || "Untitled Product", type: "product", data: body }),
        });
        loadProjects();
      } catch (e) {
        /* non-fatal: the merged data is still in memory and savable */
      }
    }
    slot.remove();
    renderEbookEnhancements(out, d, saveBarEl);
  } catch (err) {
    slot.innerHTML = card(
      `<div class="text-sm">
         <p class="font-semibold text-rose-600 mb-1">Visual enhancements failed to generate.</p>
         <p class="text-slate-500 mb-3">${escapeHtml(err.message || "Please try again.")}</p>
         <button id="retryEnhanceBtn" class="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">Retry enhancements</button>
       </div>`
    );
    const retry = slot.querySelector("#retryEnhanceBtn");
    if (retry)
      retry.addEventListener("click", () => {
        slot.remove();
        loadEbookEnhancements(out, d);
      });
  }
}

const VISUAL_AID_BADGES = {
  chart: "bg-violet-100 text-violet-700",
  graph: "bg-violet-100 text-violet-700",
  table: "bg-slate-100 text-slate-700",
  diagram: "bg-indigo-100 text-indigo-700",
  infographic: "bg-fuchsia-100 text-fuchsia-700",
  "stock photo": "bg-sky-100 text-sky-700",
  "worksheet box": "bg-blue-100 text-blue-700",
  "tip box": "bg-teal-100 text-teal-700",
  "action step box": "bg-amber-100 text-amber-700",
  "youtube resource box": "bg-rose-100 text-rose-700",
};

function aidCard(aid, packageId) {
  const badge = VISUAL_AID_BADGES[aid.type] || "bg-slate-100 text-slate-700";
  const label = (aid.type || "visual aid").replace(/\b\w/g, (c) => c.toUpperCase());
  const isImage = aid.type === "stock photo" || aid.type === "infographic";
  const rows = [];
  if (isImage) {
    const url = packageId && aid.visual_id ? `/download/${packageId}/img_${aid.visual_id}.png` : "";
    rows.push(`<div class="rounded-lg overflow-hidden border border-slate-200 bg-slate-100">
      <img data-review-vid="${escapeHtml(aid.visual_id || "")}" src="${escapeHtml(url)}" alt="${escapeHtml(aid.title || "Illustration")}" class="w-full h-28 object-cover"
        onerror="this.style.display='none';this.nextElementSibling.style.display='flex';"
        onload="this.style.display='block';this.nextElementSibling.style.display='none';">
      <div class="h-28 hidden items-center justify-center text-[11px] text-slate-400 px-2 text-center">Image will appear once generated.</div>
    </div>`);
    rows.push(`<button type="button" data-regen="${escapeHtml(aid.visual_id || "")}" data-prompt="${escapeHtml(aid.image_prompt || aid.description || aid.title || "")}"
      class="mt-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50">Regenerate</button>`);
  } else if (aid.type === "chart" || aid.type === "graph") {
    if (aid.chart_data && (aid.chart_data.labels || []).length) {
      const pairs = aid.chart_data.labels.map((l, i) => `${l}: ${aid.chart_data.values[i]}`).join(", ");
      rows.push(`<p class="text-slate-500"><span class="font-medium text-slate-600">${escapeHtml(aid.chart_data.kind)} chart:</span> ${escapeHtml(pairs)}</p>`);
    }
  } else if (aid.type === "table" && aid.table) {
    const head = (aid.table.headers || []).length ? " — " + escapeHtml(aid.table.headers.join(", ")) : "";
    rows.push(`<p class="text-slate-500">${(aid.table.rows || []).length} rows${head}</p>`);
  } else if (aid.type === "diagram" && aid.mermaid) {
    rows.push(`<p class="text-slate-500">Diagram rendered in the preview.</p>`);
  } else {
    if (aid.body) rows.push(`<p class="text-slate-600">${escapeHtml(aid.body)}</p>`);
    if ((aid.items || []).length) rows.push(`<ul class="list-disc pl-4 text-slate-600">${aid.items.slice(0, 4).map((it) => `<li>${escapeHtml(it)}</li>`).join("")}</ul>`);
  }
  if (aid.caption) rows.push(`<p class="italic text-slate-500">${escapeHtml(aid.caption)}</p>`);
  return `<div class="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs space-y-1">
    <div class="flex items-center gap-2">
      <span class="rounded-md px-2 py-0.5 font-semibold ${badge}">${escapeHtml(label)}</span>
      <span class="font-semibold text-slate-800">${escapeHtml(aid.title || "")}</span>
    </div>${rows.join("")}</div>`;
}

// Progressive, out-of-band image generation. Each gpt-image-1 call is ~30s, so we
// render the ebook immediately (with charts/tables/diagrams/boxes) and fill image
// visuals in afterwards, swapping them into the live preview iframe via postMessage.
function setupVisualImages(root, d) {
  const iframe = root.querySelector("#ebookPreviewFrame");
  const status = root.querySelector("#ebookImgStatus");

  async function generateOne(job, btn) {
    if (!d.package_id || !job || !job.visual_id) return;
    const thumb = root.querySelector(`img[data-review-vid="${job.visual_id}"]`);
    if (btn) { btn.disabled = true; btn.textContent = "Generating..."; }
    try {
      const res = await api("/render-visual-image", {
        method: "POST",
        body: JSON.stringify({ package_id: d.package_id, visual_id: job.visual_id, prompt: job.prompt || "" }),
      });
      if (res && res.ok && res.asset_url) {
        const bust = res.asset_url + "?t=" + Date.now();
        if (iframe && iframe.contentWindow) {
          iframe.contentWindow.postMessage({ type: "va-img", id: job.visual_id }, "*");
        }
        if (thumb) { thumb.src = bust; }
      }
    } catch (e) {
      /* graceful: the placeholder stays in place */
    } finally {
      if (btn) { btn.disabled = false; btn.textContent = "Regenerate"; }
    }
  }

  root.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-regen]");
    if (!btn) return;
    generateOne({ visual_id: btn.dataset.regen, prompt: btn.dataset.prompt }, btn);
  });

  const jobs = (d.image_jobs || []).filter((j) => j && j.visual_id);
  if (!d.package_id || !jobs.length || d._imagesStarted) return;
  d._imagesStarted = true;
  (async () => {
    for (let i = 0; i < jobs.length; i++) {
      if (status) status.textContent = `Generating images... (${i + 1}/${jobs.length})`;
      await generateOne(jobs[i], null);
    }
    if (status) status.textContent = "Visuals ready";
  })();
}

function renderEbookEnhancements(out, d, beforeEl) {
  const chapters = (d.visual_plan && d.visual_plan.chapters) || [];
  const aidCount = chapters.reduce((n, c) => n + ((c.aids || []).length), 0);
  const ex = d.exports || {};
  const files = ex.files || {};
  const dl = (f, label) =>
    f && f.url
      ? `<a href="${escapeHtml(f.url)}" class="btn-primary inline-flex items-center gap-2" download>${label}</a>`
      : "";

  const wrap = document.createElement("div");
  wrap.className = "space-y-6 mt-6";

  // Download section
  const dlCard = document.createElement("div");
  dlCard.innerHTML = card(
    `<h3 class="text-base font-bold text-slate-900 mb-1">Download Your Product</h3>
     <p class="text-sm text-slate-500 mb-4">Export the finished ebook with its visual plan and assets.</p>
     <div class="flex flex-wrap gap-3">
       ${dl(files.html, "Download as HTML")}
       ${dl(files.txt, "Download as TXT")}
       ${dl(files.zip, "Download Full Package ZIP")}
       <button class="btn-primary" data-send-publishing>Send to Publishing Studio</button>
     </div>
     ${ex.pdf_message ? `<p class="mt-3 text-xs rounded-lg bg-amber-50 text-amber-700 border border-amber-200 px-3 py-2">${escapeHtml(ex.pdf_message)}</p>` : ""}
     <p class="mt-3 text-xs text-slate-400">ZIP includes ebook.html, ebook.txt, visual_plan.json, cover_prompt.txt and product_summary.txt.</p>`
  );
  const sendBtn = dlCard.querySelector("[data-send-publishing]");
  if (sendBtn) sendBtn.addEventListener("click", () => sendEbookToPublishing(d, sendBtn));
  wrap.appendChild(dlCard.firstElementChild);

  // Formatted preview (with real rendered visuals: charts, tables, diagrams, images)
  if (d.preview_html) {
    const prev = document.createElement("div");
    prev.className = "rounded-2xl border border-slate-200 bg-white p-4";
    prev.innerHTML = `
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-base font-bold text-slate-900">Formatted preview</h3>
        <span id="ebookImgStatus" class="text-xs text-slate-400">with rendered visuals</span>
      </div>
      <iframe id="ebookPreviewFrame" title="Ebook preview" class="w-full rounded-xl border border-slate-200 bg-slate-100" style="height:75vh"
        sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"></iframe>`;
    wrap.appendChild(prev);
    prev.querySelector("iframe").srcdoc = d.preview_html;
  }

  // Visual enhancement plan
  if (chapters.length) {
    const planEl = document.createElement("div");
    planEl.className = "rounded-2xl border border-slate-200 bg-white p-6 space-y-4";
    const chaptersHtml = chapters
      .map(
        (c) => `<div class="space-y-2">
          <h4 class="text-sm font-semibold text-slate-800">${escapeHtml(c.chapter || "Chapter")}</h4>
          <div class="grid sm:grid-cols-2 gap-3">${(c.aids || []).map((a) => aidCard(a, d.package_id)).join("") || '<p class="text-xs text-slate-400">No visual aids.</p>'}</div>
        </div>`
      )
      .join("");
    planEl.innerHTML = `
      <div>
        <h3 class="text-base font-bold text-slate-900">Visual Review</h3>
        <p class="text-sm text-slate-500">${aidCount} rendered visual${aidCount === 1 ? "" : "s"} across ${chapters.length} chapter${chapters.length === 1 ? "" : "s"}. Image visuals can be regenerated.</p>
      </div>
      ${chaptersHtml}`;
    wrap.appendChild(planEl);
  }

  // Cover prompt + summary
  if (d.cover_prompt || d.product_summary) {
    const meta = document.createElement("div");
    meta.className = "grid sm:grid-cols-2 gap-4";
    meta.innerHTML =
      (d.cover_prompt
        ? card(`<h3 class="text-sm font-bold text-slate-900 mb-2">Cover image prompt</h3><p class="text-sm text-slate-600 whitespace-pre-wrap">${escapeHtml(d.cover_prompt)}</p>`)
        : "") +
      (d.product_summary
        ? card(`<h3 class="text-sm font-bold text-slate-900 mb-2">Product summary</h3><p class="text-sm text-slate-600 whitespace-pre-wrap">${escapeHtml(d.product_summary)}</p>`)
        : "");
    wrap.appendChild(meta);
  }

  if (beforeEl && beforeEl.parentNode === out) {
    out.insertBefore(wrap, beforeEl);
  } else {
    out.appendChild(wrap);
  }
  setupVisualImages(wrap, d);
}

async function sendEbookToPublishing(d, btn) {
  if (btn) setBusyEl(btn, true);
  try {
    // If the ebook is not yet saved, ask before creating a project.
    if (d._project_id == null) {
      const saved = await _askSaveEbook(d);
      if (!saved) {
        // User cancelled or chose not to save — go to publishing without pre-selection.
        pubState.pendingSourceId = null;
        pubState.pendingPrefill = false;
        go("publishing");
        toast("Sent to Publishing Studio. Your ebook is not yet saved — save it first to pre-select it.");
        return;
      }
      // saved === true means d._project_id was set by _askSaveEbook
    }
    pubState.pendingSourceId = d._project_id;
    pubState.pendingPrefill = true;
    go("publishing");
    toast("Sent to the Publishing Studio with your ebook selected.");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    if (btn) setBusyEl(btn, false);
  }
}

// Show a save-consent dialog for an unsaved ebook. Returns true if saved, false if declined/cancelled.
// Sets d._project_id on success.
async function _askSaveEbook(d) {
  return new Promise((resolve) => {
    const name = (d.title || "Ebook").trim();
    const overlay = document.createElement("div");
    overlay.style = "position:fixed;inset:0;background:rgba(0,0,0,0.4);z-index:999;display:flex;align-items:center;justify-content:center;padding:1rem;";
    overlay.innerHTML = `<div style="background:white;border-radius:1rem;padding:1.75rem;max-width:480px;width:100%;box-shadow:0 25px 50px rgba(0,0,0,0.25);font-family:system-ui,sans-serif;">
      <h2 style="font-size:1.125rem;font-weight:700;color:#0f172a;margin:0 0 0.75rem;">Save this ebook first?</h2>
      <p style="color:#475569;font-size:0.9rem;margin:0 0 1.5rem;line-height:1.6;">
        <strong>${escapeHtml(name)}</strong> is not saved yet. Would you like to save it before going to Publishing?<br><br>
        Saving first means Publishing Studio will open with your ebook pre-selected.
      </p>
      <div style="display:flex;flex-wrap:wrap;gap:0.75rem;justify-content:flex-end;">
        <button id="_dlgCancel" style="padding:0.625rem 1.25rem;border-radius:0.75rem;border:1px solid #cbd5e1;background:white;color:#475569;font-size:0.875rem;font-weight:500;cursor:pointer;">Cancel</button>
        <button id="_dlgNoSave" style="padding:0.625rem 1.25rem;border-radius:0.75rem;border:1px solid #cbd5e1;background:white;color:#64748b;font-size:0.875rem;font-weight:500;cursor:pointer;">Continue Without Saving</button>
        <button id="_dlgSave" style="padding:0.625rem 1.25rem;border-radius:0.75rem;border:none;background:#4f46e5;color:white;font-size:0.875rem;font-weight:600;cursor:pointer;">Save & Publish</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);

    overlay.querySelector("#_dlgSave").onclick = async () => {
      document.body.removeChild(overlay);
      try {
        const { _project_id, ...body } = d;
        body.product_type = "ebook";
        body.title = name;
        markUserSaved(body);
        const created = await api("/projects", {
          method: "POST",
          body: JSON.stringify({ name, type: "ebook", data: body }),
        });
        d._project_id = created.id;
        loadProjects();
        resolve(true);
      } catch (e) {
        toast(e.message, "error");
        resolve(false);
      }
    };
    overlay.querySelector("#_dlgNoSave").onclick = () => { document.body.removeChild(overlay); resolve(false); };
    overlay.querySelector("#_dlgCancel").onclick = () => { document.body.removeChild(overlay); resolve(false); };
    overlay.onclick = (e) => { if (e.target === overlay) { document.body.removeChild(overlay); resolve(false); } };
  });
}

function setBusyEl(btn, busy) {
  if (!btn) return;
  btn.disabled = busy;
}

// ---------- Product "Next Steps" workflow ----------
const NS_BTN =
  "rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50";

function humanizeKey(k) {
  return String(k || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function nsResult(d) {
  return d._nextStepsResult;
}

// Save (or update) the product as ONE project record. Never duplicates: a
// single-flight lock (`d._savePromise`) ensures rapid clicks before the first
// save resolves all share one create call, and once an id exists it updates in
// place. Internal `_`-prefixed fields (DOM node, promise, ids) are stripped so
// the persisted blob stays clean and JSON.stringify never hits a DOM cycle.
async function ensureProductSaved(d) {
  if (d._savePromise) {
    await d._savePromise;
    return d._project_id;
  }
  const run = (async () => {
    const name = (d.title || "").trim() || "Untitled Product";
    // AI coloring books keep the PDF under exports/<package_id>/ — never POST
    // the ~20–35 MB base64 blob (breaks Save / browser / proxies).
    const preferDiskPdf =
      d.product_type === "coloring_book" && !!(d.package_id || (d.fields && d.fields.package_id));
    let body = productSavePayload(d, { omitPdfBytes: preferDiskPdf });
    if (preferDiskPdf) {
      if (!body.package_id && d.package_id) body.package_id = d.package_id;
      if (!body.filename && d.filename) body.filename = d.filename;
      body.pdf_stored_on_disk = true;
    }
    let probe = { name, type: "product", data: body, user_saved: true };
    const tooBig = _estimateJsonBytes(probe) > 12 * 1024 * 1024; // 12 MB JSON ceiling
    if (tooBig) {
      // Other large products: persist metadata; reload PDF from disk when possible.
      body = productSavePayload(d, { omitPdfBytes: true });
      if (!body.package_id && d.package_id) body.package_id = d.package_id;
      if (!body.filename && d.filename) body.filename = d.filename;
      body.pdf_stored_on_disk = true;
      probe = { name, type: "product", data: body, user_saved: true };
    }
    let json;
    try {
      json = JSON.stringify(probe);
    } catch (err) {
      throw new Error(
        "Could not prepare project for save (payload too large or invalid). " +
          "Try again — large coloring books save metadata + package_id only."
      );
    }
    if (d._project_id != null) {
      await api(`/projects/${d._project_id}`, {
        method: "PUT",
        body: json,
      });
    } else {
      const saved = await api("/projects", {
        method: "POST",
        body: json,
      });
      if (saved && saved.id != null) d._project_id = saved.id;
    }
    d._workflow_save_pending = false;
    d._user_declined_save = false;
    markUserSaved(d);
    loadProjects();
  })();
  d._savePromise = run;
  try {
    await run;
  } finally {
    d._savePromise = null;
  }
  return d._project_id;
}

function nextStepsPanel(d) {
  const wrap = document.createElement("div");
  wrap.className = "mt-6 space-y-4";
  const head = document.createElement("div");
  const result = document.createElement("div");
  result.className = "space-y-4";
  wrap.appendChild(head);
  wrap.appendChild(result);
  d._nextStepsResult = result;

  // Universal post-save Next Steps body for non-ebook products. Only shows
  // buttons that actually work for the product type (Download PDF, Download
  // ZIP when available, Open Product, Back to Product Factory). Selling /
  // publishing options are intentionally hidden for non-ebook products
  // because the KDP / Etsy / Gumroad / Lemon Squeezy / Zazzle / Sales Page /
  // Ad Script endpoints are ebook-specific and would return 500 / Failed to
  // fetch for a coloring book, word search, crossword, math worksheet, or
  // spelling worksheet.
  //
  // Ebook uses a separate flow (ebookSaveBar -> postEbookNextSteps) and keeps
  // the 6 selling buttons because those endpoints are designed for ebooks.
  function renderPostSave() {
    const name = (d.title || "Untitled Product").trim();
    const projectId = d._project_id;
    const productType = d.product_type || "product";
    const productLabel = d.product_label || "Product";
    const coverBtnHtml = (
      productType === "crossword" ||
      productType === "word_search" ||
      productType === "coloring_book" ||
      productType === "ebook"
    )
      ? `<button data-ns="edit-cover" class="${NS_BTN} border-indigo-300 text-indigo-700 hover:bg-indigo-50">Edit Cover</button>`
      : "";
    head.innerHTML = card(
      `<span class="inline-flex items-center gap-2 rounded-full bg-emerald-600 text-white text-xs font-semibold px-3 py-1 mb-2">${escapeHtml(productLabel)} ready</span>
       <h3 class="text-lg font-bold text-slate-900">${escapeHtml(name)}</h3>
       <p class="text-sm text-slate-500 mt-1">Saved as project #${projectId}. Start with your download — extras are optional.</p>
       <div class="flex flex-wrap gap-3 mt-4">
         <button data-ns="dl-pdf" class="btn-primary">Download PDF</button>
         <button data-ns="dl-zip" class="${NS_BTN} hidden">Download ZIP package</button>
         ${coverBtnHtml}
         <button data-ns="open" class="${NS_BTN}">View in Saved Projects</button>
         <button data-ns="back" class="${NS_BTN}">Make another product</button>
       </div>
       <details class="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2">
         <summary class="cursor-pointer text-sm font-medium text-slate-700">Optional: marketing &amp; launch tools</summary>
         <div class="flex flex-wrap gap-3 mt-3">
           <button data-ns="traffic" class="${NS_BTN} border-brand-300 text-brand-700 hover:bg-brand-50">Create Traffic Content</button>
           <button data-ns="launch" class="${NS_BTN} border-amber-300 text-amber-700 hover:bg-amber-50">Create Launch Package</button>
         </div>
       </details>
       <div data-kdp-preflight-slot class="mt-4"></div>
       <p data-ns-msg class="hidden mt-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2"></p>`
    );
    const kdpSlot = head.querySelector("[data-kdp-preflight-slot]");
    if (kdpSlot) kdpSlot.appendChild(kdpPreflightPanel(d, projectId));
    const msg = head.querySelector("[data-ns-msg]");
    const editCoverBtn = head.querySelector('[data-ns="edit-cover"]');
    if (editCoverBtn) {
      editCoverBtn.onclick = () => openCoverEditor(d);
    }

    // Run /export-product to get the actual file URLs. PDF is always present
    // for these product types (they all produce PDFs). ZIP is shown only if
    // the export returns a zip file (every locked non-ebook product does).
    async function ensureExports() {
      let ex = (d.exports && d.exports.files) || (d.product_exports && d.product_exports.files);
      if (!ex) {
        const r = await api("/export-product", {
          method: "POST",
          body: JSON.stringify({ project_id: projectId }),
        });
        d.product_exports = r.exports;
        d.export_package_id = r.package_id;
        ex = r.exports && r.exports.files;
      }
      return ex || {};
    }
    function showMsg(text) { msg.textContent = text; msg.classList.remove("hidden"); }
    function hideMsg() { msg.textContent = ""; msg.classList.add("hidden"); }

    // Probe once to decide whether the ZIP button should be visible. This
    // keeps the UI honest: never show a button for a file that isn't there.
    (async () => {
      try {
        const ex = await ensureExports();
        if (ex && ex.pdf && ex.pdf.url) {
          // good — PDF is real
        }
        if (ex && ex.zip && ex.zip.url) {
          const btn = head.querySelector('[data-ns="dl-zip"]');
          if (btn) btn.classList.remove("hidden");
        }
      } catch (e) {
        // leave both hidden on error; the click handlers will show the message
      }
    })();

    const wireNs = (sel, fn) => {
      const el = head.querySelector(sel);
      if (el) el.onclick = fn;
    };
    wireNs('[data-ns="dl-pdf"]', async (e) => {
      const b = e.currentTarget;
      setBusyEl(b, true);
      try {
        const ex = await ensureExports();
        const f = ex && ex.pdf;
        if (f && f.url) {
          await triggerDownload(f.url, f.name || (name + ".pdf"));
          showMsg("PDF download started.");
        } else {
          showMsg("PDF is not available for this project yet. Try again or refresh.");
        }
      } catch (err) {
        showMsg("Could not prepare PDF: " + err.message);
      } finally {
        setBusyEl(b, false);
      }
    });
    wireNs('[data-ns="dl-zip"]', async (e) => {
      const b = e.currentTarget;
      setBusyEl(b, true);
      try {
        const ex = await ensureExports();
        const f = ex && ex.zip;
        if (f && f.url) {
          await triggerDownload(f.url, f.name || (name + ".zip"));
          showMsg("ZIP download started.");
        } else {
          showMsg("ZIP is not available for this project yet. Try again or refresh.");
        }
      } catch (err) {
        showMsg("Could not prepare ZIP: " + err.message);
      } finally {
        setBusyEl(b, false);
      }
    });
    wireNs('[data-ns="open"]', () => {
      go("saved");
      toast("Find project #" + projectId + " in Saved Projects anytime.");
    });
    wireNs('[data-ns="back"]', () => {
      go("factory");
    });
    const trafficBtn = head.querySelector('[data-ns="traffic"]');
    if (trafficBtn) {
      trafficBtn.onclick = () => {
        const ctx = {
          product_title: d.title || "",
          product_type: d.product_type || "",
          target_audience: d.target_audience || "",
          customer_problem: d.customer_problem || d.fields?.customer_problem || "",
          product_promise: d.product_promise || d.fields?.product_promise || "",
          freebie_name: d.freebie_name || "",
          landing_page_url: d.landing_page_url || "",
          tone: d.tone || "helpful and relatable",
        };
        goAdGenerator(ctx);
      };
    }
    const launchBtn = head.querySelector('[data-ns="launch"]');
    if (launchBtn) {
      launchBtn.onclick = () => {
        if (!d._project_id) {
          toast("Save the product first to create a launch package.", "error");
          return;
        }
        renderLaunchPackage(d._project_id, d);
      };
    }
  }

  // Pre-save: show a single Save Project button + Back to Factory. After save,
  // the whole head is replaced with the universal post-save body.
  function renderPreSave() {
    head.innerHTML = card(
      `<h3 class="text-base font-bold text-slate-900 mb-1">Your product is ready!</h3>
       <p class="text-sm text-slate-500 mb-4">Save it so you can download the PDF and find it later in Saved Projects.</p>
       <div class="flex flex-wrap gap-3">
         <button data-ns="save" class="btn-primary">Save &amp; download next</button>
         <button data-ns="continue-no-save" class="${NS_BTN} border-slate-300 text-slate-600 hover:bg-slate-50">Preview only (no download yet)</button>
         <button data-ns="back" class="${NS_BTN}">Back to Product Factory</button>
       </div>`
    );
    const wireBtn = (sel, fn) => {
      const b = head.querySelector(sel);
      if (b) b.onclick = () => fn(b);
    };
    wireBtn('[data-ns="save"]', async (b) => {
      setBusyEl(b, true);
      const originalLabel = b.textContent;
      b.textContent = "Saving…";
      try {
        await ensureProductSaved(d);
        toast("Saved. Download your PDF below.");
        renderPostSave();
      } catch (e) {
        console.error("Save Project failed:", e);
        toast(e.message || "Save Project failed. Check that the Flask app is running.", "error");
      } finally {
        b.textContent = originalLabel;
        setBusyEl(b, false);
      }
    });
    wireBtn('[data-ns="continue-no-save"]', async () => {
      // Mark as not saved; user stays on the product preview.
      d._user_declined_save = true;
      const saveBtn = head.querySelector('[data-ns="save"]');
      if (saveBtn) saveBtn.disabled = false;
      const noSaveBtn = head.querySelector('[data-ns="continue-no-save"]');
      if (noSaveBtn) noSaveBtn.remove();
      toast("Preview only for now. Click Save when you want to download.");
    });
    wireBtn('[data-ns="back"]', () => go("factory"));
  }

  // Store reference so _doWorkflowSave can switch to post-save UI
  d._nsRenderPostSave = renderPostSave;
  // Workflow products already have a plan `_project_id` before the user
  // confirms Save — keep the pre-save panel until they explicitly save.
  if (d._project_id != null && !d._workflow_save_pending) {
    renderPostSave();
  } else {
    renderPreSave();
  }
  return wrap;
}

async function nsPublish(d, btn) {
  setBusyEl(btn, true);
  try {
    await ensureProductSaved(d);
    pubState.pendingSourceId = d._project_id;
    pubState.pendingPrefill = true;
    go("publishing");
    toast("Sent to the Publishing Studio with your product selected.");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    setBusyEl(btn, false);
  }
}

/** Narrow KDP Preflight + Prepare Package UI for Publish/Next Steps only. */
function kdpPreflightPanel(d, projectId) {
  const wrap = document.createElement("div");
  const defaultFmt = (d.product_type === "ebook") ? "ebook" : "paperback";
  wrap.innerHTML = card(
    `<h4 class="text-sm font-bold text-slate-900 mb-1">Amazon KDP Preflight</h4>
     <p class="text-xs text-slate-500 mb-3">Choose format and settings, complete metadata and AI disclosure, then run preflight. Ordinary PDF/ZIP downloads are unchanged.</p>
     <div class="grid gap-2 sm:grid-cols-2 text-sm">
       <label class="block">Publication format
         <select data-kdp="format" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5">
           <option value="paperback">Paperback</option>
           <option value="ebook">Ebook</option>
           <option value="hardcover">Hardcover (unsupported)</option>
         </select>
       </label>
       <label class="block">Ink
         <select data-kdp="ink" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5">
           <option value="black">Black</option>
           <option value="standard_color">Standard color</option>
           <option value="premium_color">Premium color</option>
         </select>
       </label>
       <label class="block">Paper
         <select data-kdp="paper" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5">
           <option value="white">White</option>
           <option value="cream">Cream</option>
           <option value="groundwood">Groundwood</option>
         </select>
       </label>
       <label class="block">Trim
         <select data-kdp="trim" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5">
           <option value="6x9">6 x 9</option>
           <option value="8.5x11">8.5 x 11</option>
           <option value="8.5x8.5">8.5 x 8.5</option>
           <option value="5x8">5 x 8</option>
         </select>
       </label>
       <label class="block">Bleed
         <select data-kdp="bleed" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5">
           <option value="with_bleed">With bleed</option>
           <option value="no_bleed">No bleed</option>
         </select>
       </label>
       <label class="block">Page count (optional override)
         <input data-kdp="page_count" type="number" min="1" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5" placeholder="Auto from PDF">
       </label>
       <label class="block sm:col-span-2">Title
         <input data-kdp="title" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5" value="${escapeHtml(d.title || d.listing_title || "")}">
       </label>
       <label class="block">Author
         <input data-kdp="author" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5" value="${escapeHtml(d.author_name || d.author || "")}">
       </label>
       <label class="block">ISBN option
         <select data-kdp="isbn_option" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5">
           <option value="none">None / not set</option>
           <option value="own">Own ISBN</option>
           <option value="kdp_free">Free KDP ISBN (eligibility)</option>
           <option value="publish_without">Publish without (low-content)</option>
         </select>
       </label>
       <label class="block sm:col-span-2">ISBN (caller-supplied only)
         <input data-kdp="isbn" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5" placeholder="978…">
       </label>
       <label class="block">AI text
         <select data-kdp="ai_text" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5">
           <option value="unknown">Unknown</option>
           <option value="none">None</option>
           <option value="ai_assisted">AI-assisted</option>
           <option value="ai_generated">AI-generated</option>
         </select>
       </label>
       <label class="block">AI images
         <select data-kdp="ai_images" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5">
           <option value="unknown">Unknown</option>
           <option value="none">None</option>
           <option value="ai_assisted">AI-assisted</option>
           <option value="ai_generated">AI-generated</option>
         </select>
       </label>
       <label class="block sm:col-span-2">AI translations
         <select data-kdp="ai_translations" class="mt-1 w-full rounded-lg border border-slate-300 px-2 py-1.5">
           <option value="unknown">Unknown</option>
           <option value="none">None</option>
           <option value="ai_assisted">AI-assisted</option>
           <option value="ai_generated">AI-generated</option>
         </select>
       </label>
     </div>
     <div class="flex flex-wrap gap-3 mt-4">
       <button data-kdp-act="run" class="btn-primary">Run KDP Preflight</button>
       <button data-kdp-act="prepare" class="${NS_BTN}" disabled>Prepare KDP Package</button>
     </div>
     <label class="hidden mt-3 flex items-start gap-2 text-xs text-amber-900" data-kdp-ack-wrap>
       <input type="checkbox" data-kdp-ack class="mt-0.5">
       <span>I reviewed all WARNING findings and accept human responsibility before Prepare KDP Package.</span>
     </label>
     <div data-kdp-result class="mt-3 text-sm"></div>`
  );
  const fmtEl = wrap.querySelector('[data-kdp="format"]');
  if (fmtEl) fmtEl.value = defaultFmt;
  const resultEl = wrap.querySelector("[data-kdp-result]");
  const prepareBtn = wrap.querySelector('[data-kdp-act="prepare"]');
  const ackWrap = wrap.querySelector("[data-kdp-ack-wrap]");
  const ackEl = wrap.querySelector("[data-kdp-ack]");
  let lastPreflight = null;

  function collectPayload() {
    const trim = (wrap.querySelector('[data-kdp="trim"]').value || "6x9").split("x");
    const pageRaw = wrap.querySelector('[data-kdp="page_count"]').value;
    const print_settings = {
      binding: "paperback",
      ink: wrap.querySelector('[data-kdp="ink"]').value,
      paper: wrap.querySelector('[data-kdp="paper"]').value,
      trim_width_in: trim[0],
      trim_height_in: trim[1],
      bleed: wrap.querySelector('[data-kdp="bleed"]').value,
    };
    if (pageRaw) print_settings.page_count = Number(pageRaw);
    return {
      publication_format: wrap.querySelector('[data-kdp="format"]').value,
      print_settings,
      metadata: {
        title: wrap.querySelector('[data-kdp="title"]').value,
        author: wrap.querySelector('[data-kdp="author"]').value,
        isbn: wrap.querySelector('[data-kdp="isbn"]').value,
        isbn_option: wrap.querySelector('[data-kdp="isbn_option"]').value,
        product_type: d.product_type || "",
      },
      ai_disclosure: {
        text: wrap.querySelector('[data-kdp="ai_text"]').value,
        images: wrap.querySelector('[data-kdp="ai_images"]').value,
        translations: wrap.querySelector('[data-kdp="ai_translations"]').value,
      },
    };
  }

  function renderFindings(r) {
    lastPreflight = r;
    const overall = r.overall || "";
    let tone = "bg-slate-50 border-slate-200 text-slate-800";
    if (overall.indexOf("PASS") === 0) tone = "bg-emerald-50 border-emerald-200 text-emerald-900";
    else if (overall.indexOf("WARNING") === 0) tone = "bg-amber-50 border-amber-200 text-amber-900";
    else if (overall.indexOf("FAIL") === 0) tone = "bg-rose-50 border-rose-200 text-rose-900";
    const findings = Array.isArray(r.findings) ? r.findings : [];
    const rows = findings.map((f) =>
      `<li class="mb-2"><span class="font-semibold">${escapeHtml(f.severity)}</span> · ${escapeHtml(f.rule_id)} · <span class="text-slate-600">${escapeHtml(f.affected || "")}</span><br>${escapeHtml(f.explanation || "")}<br><span class="text-xs">Fix: ${escapeHtml(f.required_correction || "")}</span></li>`
    ).join("");
    resultEl.innerHTML =
      `<div class="rounded-lg border px-3 py-2 ${tone}"><p class="font-bold">${escapeHtml(overall)}</p>
       <p class="text-xs mt-1">Never “Guaranteed Amazon Approved.”</p></div>
       <ul class="mt-3 max-h-64 overflow-auto text-xs">${rows}</ul>`;
    prepareBtn.disabled = true;
    ackWrap.classList.add("hidden");
    if (overall.indexOf("PASS") === 0) {
      prepareBtn.disabled = false;
    } else if (overall.indexOf("WARNING") === 0) {
      ackWrap.classList.remove("hidden");
      prepareBtn.disabled = !(ackEl && ackEl.checked);
    }
  }

  if (ackEl) {
    ackEl.onchange = () => {
      if (lastPreflight && String(lastPreflight.overall || "").indexOf("WARNING") === 0) {
        prepareBtn.disabled = !ackEl.checked;
      }
    };
  }

  wrap.querySelector('[data-kdp-act="run"]').onclick = async (e) => {
    const btn = e.currentTarget;
    setBusyEl(btn, true);
    resultEl.innerHTML = spinner("Running KDP preflight…");
    try {
      const payload = collectPayload();
      const r = await api(`/projects/${projectId}/kdp/preflight`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      d.kdp_preflight = r;
      renderFindings(r);
    } catch (err) {
      lastPreflight = null;
      prepareBtn.disabled = true;
      resultEl.innerHTML = `<p class="text-rose-600">${escapeHtml(err.message || String(err))}</p>`;
    } finally {
      setBusyEl(btn, false);
    }
  };

  prepareBtn.onclick = async () => {
    if (!lastPreflight || !lastPreflight.preflight_token) {
      toast("Run KDP Preflight first.", "error");
      return;
    }
    setBusyEl(prepareBtn, true);
    try {
      const payload = collectPayload();
      payload.preflight_token = lastPreflight.preflight_token;
      payload.warning_acknowledged = !!(ackEl && ackEl.checked);
      const r = await api(`/projects/${projectId}/kdp/prepare-package`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      d.kdp_package_manifest = r.manifest;
      resultEl.innerHTML +=
        `<div class="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-900">
          <p class="font-bold">${escapeHtml(r.label || "Ready for Amazon Previewer")}</p>
          <p class="text-xs mt-1">${escapeHtml(r.note || "")}</p>
         </div>`;
      toast("KDP package gate accepted (manifest written).");
    } catch (err) {
      toast(err.message || "Prepare KDP Package blocked", "error");
      resultEl.innerHTML += `<p class="mt-2 text-rose-600 text-xs">${escapeHtml(err.message || String(err))}</p>`;
    } finally {
      setBusyEl(prepareBtn, false);
    }
  };

  return wrap;
}

// Unified "Final Output Options" shown after a product is completed (Export
// Product) or after a publishing layout is saved: basic downloads (PDF / HTML /
// TXT / ZIP) plus on-demand platform packages. Each platform package is
// generated ONLY when its button is clicked, and persists to the SAME project.
function finalOutputCard(projectId, ex, existingPackages, productType) {
  existingPackages = existingPackages || {};
  const f = (ex && ex.files) || {};
  const dl = (file, label) =>
    file && file.url
      ? `<a href="${escapeHtml(file.url)}" class="${NS_BTN}" download="${escapeHtml(file.name || "")}" data-export-dl>${escapeHtml(label)}</a>`
      : "";
  const platRows = PLATFORMS.map((p) => {
    const made = !!existingPackages[p.id];
    return `<div>
        <button data-platform="${p.id}" class="${NS_BTN}">Create ${escapeHtml(p.label)} Package${
      made ? ' <span data-created class="ml-2 text-emerald-600 font-semibold">Created</span>' : ""
    }</button>
        <div data-result="${p.id}" class="mt-3">${made ? packageCardHtml(p.title, existingPackages[p.id]) : ""}</div>
      </div>`;
  }).join("");
  return card(
    `<h3 class="text-base font-bold text-slate-900 mb-1">Final Output Options</h3>
     <p class="text-sm text-slate-500 mb-5">Download your finished product, or prepare a marketplace listing on demand.</p>
     <div class="mb-6">
       <p class="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">Basic Downloads</p>
        <div class="flex flex-wrap gap-3">
          ${(productType === "word_search" || productType === "crossword")
            ? `<button class="${NS_BTN}" data-pdf>Download PDF</button>`
            : dl(f.pdf, "Download PDF")}
          ${dl(f.html, "Download HTML")}
         ${dl(f.txt, "Download TXT")}
         ${dl(f.zip, "Download ZIP Package")}
       </div>
       <p data-pdf-msg class="hidden mt-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2"></p>
     </div>
     <div data-platform-row data-project="${escapeHtml(String(projectId))}">
       <p class="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1">Optional Platform Packages</p>
       <p class="text-sm text-slate-500 mb-3">Each package is generated only when you click its button.</p>
       <div class="space-y-4">${platRows}</div>
     </div>`
  );
}

function wireFinalOutputIn(container, projectId, ex) {
  if (!container) return;
  const pid = projectId != null ? projectId : (container.querySelector("[data-platform-row]") || {}).dataset?.project;
  // PDF: real download for puzzle products, placeholder message for others.
  const pdfBtn = container.querySelector("[data-pdf]");
  const pdfMsg = container.querySelector("[data-pdf-msg]");
  if (pdfBtn) {
    const pdfFile = ex && ex.files && ex.files.pdf;
    if (pdfFile && pdfFile.url) {
      // Replace button with a real download link
      const a = document.createElement("a");
      a.href = pdfFile.url;
      a.download = pdfFile.name || "puzzle.pdf";
      a.className = NS_BTN;
      a.setAttribute("data-export-dl", "");
      a.textContent = "Download PDF";
      pdfBtn.replaceWith(a);
    } else {
      pdfBtn.onclick = () => {
        if (pdfMsg) {
          pdfMsg.textContent = "PDF export is not available for this product type.";
          pdfMsg.classList.remove("hidden");
        }
      };
    }
  }
  // A real download click is the true "completed" event for the project.
  container
    .querySelectorAll("a[data-export-dl]")
    .forEach((a) => a.addEventListener("click", () => markCompletedById(pid)));
  // Platform buttons generate ONE package on click into their own result slot.
  container.querySelectorAll("[data-platform]").forEach((b) => {
    const plat = PLATFORMS.find((p) => p.id === b.dataset.platform);
    if (!plat) return;
    const resultEl = container.querySelector(`[data-result="${plat.id}"]`);
    b.onclick = async () => {
      await createPlatformPackage(pid, plat, b, resultEl);
      if (!b.querySelector("[data-created]"))
        b.insertAdjacentHTML("beforeend", ' <span data-created class="ml-2 text-emerald-600 font-semibold">Created</span>');
    };
  });
}

async function nsExport(d, btn) {
  setBusyEl(btn, true);
  const res = nsResult(d);
  if (res) res.innerHTML = spinner("Preparing your downloads...");
  try {
    await ensureProductSaved(d);
    // Reuse a rich ebook export package if it already exists; otherwise build a
    // generic HTML/TXT/ZIP export for this product type.
    // Must check .files on product_exports too — an empty {} is truthy but has no files.
    let ex =
      (d.exports && d.exports.files) || (d.product_exports && d.product_exports.files)
        ? d.exports || d.product_exports
        : null;
    if (!ex) {
      const r = await api("/export-product", {
        method: "POST",
        body: JSON.stringify({ project_id: d._project_id }),
      });
      d.product_exports = r.exports;
      d.export_package_id = r.package_id;
      ex = r.exports;
    }
    if (res) {
      // Final Output Options: basic downloads + on-demand platform packages.
      res.innerHTML = finalOutputCard(d._project_id, ex, d.packages || {}, d.product_type);
      wireFinalOutputIn(res, d._project_id, ex);
    }
  } catch (e) {
    if (res) res.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusyEl(btn, false);
  }
}

function packageCardHtml(label, pkg) {
  const skip = new Set(["platform", "platform_label"]);
  const rows = Object.entries(pkg || {})
    .filter(([k]) => !skip.has(k))
    .map(([k, v]) => {
      let body;
      if (Array.isArray(v)) {
        body = v.length
          ? `<ul class="list-disc pl-5 text-sm text-slate-600 space-y-0.5">${v
              .map((it) => `<li>${escapeHtml(typeof it === "string" ? it : JSON.stringify(it))}</li>`)
              .join("")}</ul>`
          : `<p class="text-sm text-slate-400">—</p>`;
      } else {
        body = `<p class="text-sm text-slate-600 whitespace-pre-wrap">${escapeHtml(v || "—")}</p>`;
      }
      return `<div><h4 class="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">${escapeHtml(
        humanizeKey(k)
      )}</h4>${body}</div>`;
    })
    .join("");
  return card(
    `<h3 class="text-base font-bold text-slate-900 mb-3">${escapeHtml(label)} Package</h3>
     <div class="grid sm:grid-cols-2 gap-4">${rows}</div>`
  );
}

async function nsPackage(d, platform, label, btn) {
  setBusyEl(btn, true);
  const res = nsResult(d);
  if (res) res.innerHTML = spinner(`Building your ${label} package...`);
  try {
    await ensureProductSaved(d);
    const r = await api("/generate-seller-package", {
      method: "POST",
      body: JSON.stringify({ project_id: d._project_id, platform }),
    });
    if (!d.packages) d.packages = {};
    d.packages[platform] = r.package;
    if (res) res.innerHTML = packageCardHtml(label, r.package);
  } catch (e) {
    if (res) res.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusyEl(btn, false);
  }
}

async function nsSalesPage(d, btn) {
  setBusyEl(btn, true);
  const res = nsResult(d);
  if (res) res.innerHTML = spinner("Writing your sales page...");
  try {
    await ensureProductSaved(d);
    const r = await api("/generate-sales-page", {
      method: "POST",
      body: JSON.stringify({ project_id: d._project_id }),
    });
    d.sales_page = r.sales_page;
    if (res)
      res.innerHTML = card(
        `<h3 class="text-base font-bold text-slate-900 mb-3">Sales Page</h3><div class="prose-out">${md(
          r.sales_page
        )}</div>`
      );
  } catch (e) {
    if (res) res.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusyEl(btn, false);
  }
}

async function nsAdScript(d, btn) {
  setBusyEl(btn, true);
  const res = nsResult(d);
  if (res) res.innerHTML = spinner("Writing your 30s and 60s ad scripts...");
  try {
    await ensureProductSaved(d);
    const r = await api("/generate-product-ad", {
      method: "POST",
      body: JSON.stringify({ project_id: d._project_id }),
    });
    d.ad_scripts = { ad_30: r.ad_30, ad_60: r.ad_60 };
    if (res)
      res.innerHTML = card(
        `<h3 class="text-base font-bold text-slate-900 mb-3">Video Ad Scripts</h3>
         <h4 class="text-sm font-semibold text-slate-800 mb-2">30-Second Script</h4>
         <div class="prose-out mb-6">${md(r.ad_30 || "")}</div>
         <h4 class="text-sm font-semibold text-slate-800 mb-2">60-Second Script</h4>
         <div class="prose-out">${md(r.ad_60 || "")}</div>`
      );
  } catch (e) {
    if (res) res.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusyEl(btn, false);
  }
}

// ---------- platform packages ----------
const PLATFORMS = [
  { id: "kdp", label: "KDP", title: "Amazon KDP", desc: "Kindle Direct Publishing listing: title, 7 keywords, categories, descriptions, backend search terms, and cover/manuscript/upload checklists." },
  { id: "etsy", label: "Etsy", title: "Etsy", desc: "Etsy listing: SEO title, 13 tags, short and long descriptions, image ideas, buyer files, listing bullets, and FAQ." },
  { id: "gumroad", label: "Gumroad", title: "Gumroad", desc: "Gumroad product: name, sales page copy, included files, customer benefits, FAQ, and a thank-you message." },
  { id: "lemon_squeezy", label: "Lemon Squeezy", title: "Lemon Squeezy", desc: "Lemon Squeezy product: name, sales headline, benefits, download list, fulfillment, refund terms, and delivery message." },
  { id: "zazzle", label: "Zazzle", title: "Zazzle", desc: "Zazzle product: title, description, tags, design placement notes, product mockup guidance, and recommended product types." },
];
const PACKAGE_READY_STAGES = ["publishing_preview_ready", "export_ready", "completed"];
let packageProjects = [];

// Generate ONE marketplace seller package on demand and render it into resultEl.
// Persists to the SAME project record (backend writes data.packages[platform]).
async function createPlatformPackage(projectId, plat, btn, resultEl) {
  setBusyEl(btn, true);
  if (resultEl) resultEl.innerHTML = spinner(`Building your ${plat.title} package...`);
  try {
    const r = await api("/generate-seller-package", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, platform: plat.id }),
    });
    if (resultEl) resultEl.innerHTML = packageCardHtml(plat.title, r.package);
  } catch (e) {
    if (resultEl) resultEl.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusyEl(btn, false);
  }
}

async function initPackages() {
  await loadPackageSources();
}

async function loadPackageSources() {
  const sel = document.getElementById("packageSource");
  const out = document.getElementById("packageOutput");
  if (!sel) return;
  let projects = [];
  try { projects = await api("/projects"); } catch (e) { /* ignore */ }
  packageProjects = projects.filter((p) => p.type === "product" || p.type === "ebook");
  if (!packageProjects.length) {
    sel.innerHTML = `<option value="">No products yet</option>`;
    if (out) out.innerHTML = card(`<p class="text-sm text-slate-400">No products yet. Build a product in the Product Factory and complete it in the Publishing Studio first.</p>`);
    return;
  }
  sel.innerHTML =
    `<option value="">Choose a product...</option>` +
    packageProjects
      .map((p) => `<option value="${p.id}">${escapeHtml(p.name)} — ${escapeHtml(STAGE_LABELS[projectStage(p)] || "Draft")}</option>`)
      .join("");
  sel.onchange = () => {
    const proj = packageProjects.find((p) => String(p.id) === String(sel.value));
    renderPackageOptions(proj, out);
  };
  if (out) out.innerHTML = card(`<p class="text-sm text-slate-400">Select a product above to create its platform packages.</p>`);
}

function renderPackageOptions(proj, out) {
  if (!out) return;
  if (!proj) { out.innerHTML = ""; return; }
  const stage = projectStage(proj);
  if (!PACKAGE_READY_STAGES.includes(stage)) {
    out.innerHTML = card(
      `<p class="inline-flex items-start gap-2 rounded-lg bg-amber-50 text-amber-800 border border-amber-200 px-4 py-3 text-sm font-medium">This project needs to be completed in Publishing Studio before platform packages can be created.</p>`
    );
    return;
  }
  const existing = (proj.data && proj.data.packages) || {};
  out.innerHTML = "";
  PLATFORMS.forEach((plat) => {
    const cardEl = document.createElement("div");
    cardEl.innerHTML = card(
      `<div class="flex flex-wrap items-center justify-between gap-3 mb-2">
         <h3 class="text-base font-bold text-slate-900">${escapeHtml(plat.title)} Package</h3>
         <button data-create class="${NS_BTN}">Create ${escapeHtml(plat.label)} Package</button>
       </div>
       <p class="text-sm text-slate-500">${escapeHtml(plat.desc)}</p>
       <div data-result class="mt-4"></div>`
    );
    const resultEl = cardEl.querySelector("[data-result]");
    const btn = cardEl.querySelector("[data-create]");
    if (btn) btn.onclick = () => createPlatformPackage(proj.id, plat, btn, resultEl);
    if (existing[plat.id] && resultEl) resultEl.innerHTML = packageCardHtml(plat.title, existing[plat.id]);
    out.appendChild(cardEl);
  });
}

async function runProduct() {
  if (!factoryType) return toast("Pick a product type first", "error");
  const t = productType(factoryType);
  const fields = collectFactoryFields();
  const requiredMissing = t.fields.filter((f) => f.required && !(fields[f.name] || "").trim());
  if (requiredMissing.length) return toast(`${requiredMissing[0].label} is required`, "error");

  // Workflow case: Market Research → Plan → Factory chain. Remember it BEFORE
  // clearing pendingProductProjectId, so the post-render auto-save + auto-PDF
  // download can run for the chain. The whole point of Research → Plan →
  // Factory is "send me a downloadable product" — the user shouldn't have to
  // click a second button after Generate.
  const wasWorkflow = pendingProductProjectId != null;

  const out = document.getElementById("factoryOutput");
  const waitNote =
    factoryType === "coloring_book"
      ? "Creating your coloring book… This can take a few minutes. We’ll show a cover preview to approve when needed."
      : `Generating your ${t.label.toLowerCase()}…`;
  out.innerHTML = spinner(waitNote);
  setBusy("factoryBtn", true);
  try {
    const data = await api("/generate-product", {
      method: "POST",
      body: JSON.stringify({ product_type: factoryType, fields }),
    });
    data.stage = "product_generated";
    if (wasWorkflow) {
      data._project_id = pendingProductProjectId; // advance the plan record into a product
      pendingProductProjectId = null;
      // Plan id is already present; keep Next Steps on pre-save until consent.
      if (data._project_id != null) data._workflow_save_pending = true;
    }
    renderProduct(data);
    // Bring the Next Steps panel into view so the user sees Save / Download
    // actions after generate. The panel is appended AFTER the preview card.
    scrollNextStepsPanelIntoView(data);

    // Ask before saving workflow products. Don't auto-save without consent.
    // Manual one-off products use the Next Steps 'Save Project' button.
    if (wasWorkflow && data._project_id != null) {
      _showWorkflowSaveDialog(data, () => _doWorkflowSave(data));
    }
  } catch (e) {
    out.innerHTML = card(
      `<p class="text-rose-600 text-sm font-medium mb-2">${escapeHtml(e.message)}</p>
       <p class="text-sm text-slate-600 mb-3">Fix any missing fields above, then try Generate again.</p>
       <button id="factoryRetryBtn" class="btn-primary">Try again</button>`
    );
    const retry = document.getElementById("factoryRetryBtn");
    if (retry) retry.onclick = () => runProduct();
  } finally {
    setBusy("factoryBtn", false);
  }
}

// Scroll the Next Steps panel into view. Used by runProduct() in the workflow
// case so the user lands on the Download PDF / Download ZIP / Open Product /
// Back to Factory panel right after the auto-download starts. The panel is
// stored on `d._nextStepsResult` by nextStepsPanel().
function scrollNextStepsPanelIntoView(d) {
  if (!d || !d._nextStepsResult) return;
  const wrap = d._nextStepsResult.parentElement;
  if (wrap && typeof wrap.scrollIntoView === "function") {
    try {
      wrap.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      /* non-fatal: some browsers reject smooth on detached elements */
    }
  }
}

// ---------- research ----------
function renderResearch(d) {
  const out = document.getElementById("researchOutput");
  const rawResults = d.raw_search_results || d.results || [];
  const ops = d.opportunities || d.recommended_product_opportunities || [];
  const reco = d.recommendation || d.best_recommendation || {};
  // Normalize to the discovery shape so the shared buttons/helpers work.
  const dd = { opportunities: ops, recommendation: reco, mode: d.mode, keyword: d.keyword };

  const rawCards = rawResults
    .map(
      (r) => `<a href="${escapeHtml(r.url)}" target="_blank" rel="noopener"
        class="block rounded-xl border border-slate-100 hover:border-brand-200 px-4 py-3 transition">
        <div class="font-medium text-slate-800 truncate">${escapeHtml(r.title)}</div>
        <div class="text-xs text-brand-600 truncate">${escapeHtml(r.url)}</div>
        <div class="text-sm text-slate-500 mt-1 line-clamp-2">${escapeHtml(r.content)}</div></a>`
    )
    .join("");

  const rawSection = card(
    `<div class="flex flex-wrap items-center justify-between gap-3 mb-3">
       <h3 class="text-base font-bold text-slate-900">Raw Search Results</h3>
       <div class="flex items-center gap-3">
         ${modeBadgeHtml(d.mode)}
         <button id="saveResearchBtn" class="rounded-xl border border-slate-300 text-slate-600 hover:bg-slate-50 px-3 py-1.5 text-sm font-medium">Save Research Only</button>
       </div>
     </div>` +
      (rawResults.length
        ? `<div class="space-y-2">${rawCards}</div>`
        : '<p class="text-sm text-slate-500">No live web results were returned.</p>')
  );

  if (!ops.length) {
    out.innerHTML = rawSection;
    lastDiscovery = dd;
    const saveBtn = out.querySelector("#saveResearchBtn");
    if (saveBtn) saveBtn.onclick = saveResearchOnly;
    return;
  }

  out.innerHTML =
    rawSection +
    `<div class="space-y-4 mt-6">
      <h3 class="text-base font-bold text-slate-900">Recommended Product Opportunities</h3>
      <p class="text-sm text-slate-500">Pick an opportunity with <span class="font-medium text-slate-700">Choose This Idea</span>, or jump to the strongest with <span class="font-medium text-slate-700">Use Best Recommendation</span> to start planning your product.</p>
      <div class="space-y-4">${opportunityCardsHtml(ops)}</div>
      ${recommendationCardHtml(reco)}
    </div>`;

  dd._rerender = () => renderResearch(d);
  wireOpportunityButtons(out, dd);
}

async function runResearch() {
  const keyword = document.getElementById("researchInput").value.trim();
  if (!keyword) return toast("Enter a keyword", "error");
  const out = document.getElementById("researchOutput");
  out.innerHTML = spinner("Researching the web and ranking product opportunities...");
  setBusy("researchBtn", true);
  try {
    const data = await api("/research", { method: "POST", body: JSON.stringify({ keyword }) });
    renderResearch(data);
  } catch (e) {
    out.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusy("researchBtn", false);
  }
}

// ---------- ebook ----------
async function renderEbook(d) {
  const out = document.getElementById("ebookOutput");
  out.innerHTML = card(
    // Title row: source-type badge + title on the left, "Download PDF" on the
    // right. The button is the prominent one-click download for the preview
    // card. After the user saves the project (or auto-save fires below), the
    // Post-Save Next Steps panel renders below with the full Download PDF / ZIP
    // / Open / Selling set.
    `<div class="flex items-center justify-between gap-3 mb-3">
       <div class="flex items-center gap-2 text-xs text-slate-500 min-w-0">
         <span class="rounded-md bg-brand-100 text-brand-700 font-semibold px-2 py-0.5">${escapeHtml(d.source_type || "ebook")}</span>
         <span class="truncate">${escapeHtml(d.title || d.source || "Ebook")}</span>
       </div>
       <button data-ebook-preview-dl class="${NS_BTN}">Download PDF</button>
     </div><div class="prose-out">${md(d.ebook)}</div>`
  );
  // Normalize the ebook-builder data shape so downstream code (loadEbookEnhancements,
  // postEbookNextSteps, save flows) can use the same field names the Product
  // Factory path produces. The /generate-ebook endpoint returns {ebook, source,
  // source_type}; everything else in the factory expects {content, title,
  // product_type}.
  d.content = d.content || d.ebook || "";
  d.title = d.title || d.source || "Ebook";
  d.product_type = d.product_type || "ebook";
  d.fields = d.fields || {};
  // Wire the preview-card "Download PDF" button. It reuses the same
  // /export-product endpoint as the post-save panel — requires a saved project
  // (tells the user to save if not yet saved).
  const previewDl = out.querySelector("[data-ebook-preview-dl]");
  if (previewDl) {
    previewDl.onclick = async (e) => {
      const b = e.currentTarget;
      setBusyEl(b, true);
      try {
        const projectId = d._project_id;
        if (projectId == null) {
          toast("Save the project first to download.", "error");
          return;
        }
        let ex = (d.exports && d.exports.files) || (d.product_exports && d.product_exports.files);
        if (!ex) {
          const r = await api("/export-product", {
            method: "POST",
            body: JSON.stringify({ project_id: projectId }),
          });
          d.product_exports = r.exports;
          d.export_package_id = r.package_id;
          ex = r.exports && r.exports.files;
        }
        const f = ex && ex.pdf;
        if (f && f.url) {
          await triggerDownload(f.url, f.name || ((d.title || "ebook") + ".pdf"));
          toast("Your PDF is downloading.");
        } else {
          toast("PDF is not available for this project yet.", "error");
        }
      } catch (err) {
        toast("Could not prepare PDF: " + err.message, "error");
      } finally {
        setBusyEl(b, false);
      }
    };
  }
  // Workflow case: sendToBuilder (or runNextAction) attached pendingEbookBrief
  // with a saved project_id from the Saved Plan. Auto-save the freshly
  // generated ebook in place, then auto-trigger the PDF download + render the
  // Post-Save Next Steps panel. The user clicked "Build Product" expecting a
  // built, downloadable ebook — no second click required.
  const workflowProjectId = pendingEbookBrief && pendingEbookBrief._project_id;
  if (workflowProjectId && d._project_id == null) {
    d._project_id = workflowProjectId;
  }
  if (d._project_id != null && d.product_type === "ebook") {
    // Already-saved ebook (workflow case OR user reopening from Saved Projects).
    // Render the post-save panel directly with Download PDF / ZIP / Open / Selling
    // buttons — no save bar. For the workflow case, autoSaveEbookForWorkflow
    // is also called below to persist the new content + auto-fire the download.
    const postPanel = await postEbookNextSteps(d, d._project_id, d.title || d.source || "Ebook");
    out.appendChild(postPanel);
  } else {
    // Fresh, unsaved ebook (direct Ebook Builder entry, no saved plan).
    // Show the save bar (replaces itself with the post-save panel after the
    // user clicks Save as Project).
    const saveBarEl = ebookSaveBar(d);
    out.appendChild(saveBarEl);
    // Auto-build the cover + visual plan in the background. Skipped if
    // d.preview_html or d.visual_plan is already set (reopened project).
    if (d.product_type === "ebook" && !d.preview_html && !d.visual_plan) {
      loadEbookEnhancements(out, d, saveBarEl);
    }
  }
  // Workflow case: auto-save the freshly generated content + auto-trigger
  // PDF download + replace the post-save panel contents with the latest
  // data. Runs after the initial post-save panel is rendered above so the
  // user always sees a response.
  if (workflowProjectId) {
    autoSaveEbookForWorkflow(d, null);
  }
}

// Auto-save the freshly-generated ebook into the existing workflow project.
// Fires the PDF download automatically (the whole point of the chain is
// "give me a downloadable product"). Also replaces the pre-save area with the
// Post-Save Next Steps panel if saveBarEl is provided (legacy direct call
// path). In the new renderEbook path, the post-save panel is already rendered
// before this fires, so saveBarEl is null and we just persist + download.
//
// The toast and download fire from inside the Build Product click handler
// chain (sendToBuilder -> runEbook -> renderEbook -> autoSaveEbookForWorkflow),
// which preserves the user-gesture chain so triggerDownload is allowed by
// the browser.
async function autoSaveEbookForWorkflow(d, saveBarEl) {
  const name = d.title || "Ebook";
  try {
    const body = { ...d };
    body.product_type = "ebook";
    body.title = name;
    markUserSaved(body);
    const saved = await api(`/projects/${d._project_id}`, {
      method: "PUT",
      body: JSON.stringify({ name, type: "ebook", data: body }),
    });
    if (saved && saved.id != null) d._project_id = saved.id;
    loadProjects();
    // Now fetch the export package and fire the download. The whole point of
    // the Research -> Plan -> Build chain is "give me a downloadable product"
    // — the user shouldn't have to click Download after the build finishes.
    // /export-product is the same endpoint the manual button uses and the
    // file bytes are identical for the same project. Prefer PDF; fall back
    // to ZIP if PDF generation failed (some product types don't always
    // produce a PDF on first try).
    let firedDownload = false;
    try {
      const r = await api("/export-product", {
        method: "POST",
        body: JSON.stringify({ project_id: d._project_id }),
      });
      const files = (r && r.exports && r.exports.files) || {};
      d.product_exports = r.exports;
      d.export_package_id = r.package_id;
      const pdfF = files.pdf;
      const zipF = files.zip;
      if (pdfF && pdfF.url) {
        await triggerDownload(pdfF.url, pdfF.name || (name + ".pdf"));
        toast("Your PDF is downloading. Find it in your browser's downloads.");
        firedDownload = true;
      } else if (zipF && zipF.url) {
        await triggerDownload(zipF.url, zipF.name || (name + ".zip"));
        toast("Your ZIP package is downloading. PDF wasn't available but the ZIP has the full content.");
        firedDownload = true;
      }
    } catch (e) {
      /* non-fatal: the post-save panel still has a manual Download PDF/ZIP button */
    }
    // Legacy: if the pre-save area is still around, swap it for the post-save
    // panel. In the new renderEbook flow the panel is already rendered.
    if (saveBarEl && saveBarEl.parentNode) {
      const preSave = saveBarEl.firstElementChild;
      if (preSave) preSave.remove();
      saveBarEl.appendChild(await postEbookNextSteps(d, saved.id, name));
    }
    if (!firedDownload && !saveBarEl) {
      toast("Ebook built and saved to project #" + saved.id + ". Click Download PDF in the panel below.");
    }
  } catch (e) {
    toast("Built the ebook but could not auto-save: " + e.message + ". Click Save as Project to retry.", "error");
  }
}

// Save the ebook as a project (type="ebook") and, on success, render the
// Post-Save Next Steps panel right under the content. This restores the
// download + sell flow that the generic saveBar silently dropped.
function ebookSaveBar(d) {
  const wrap = document.createElement("div");
  wrap.className = "mt-4 space-y-4";

  // Connected Ebook Builder workflow (Stabilized recovery) — visible controls.
  const workflow = document.createElement("div");
  workflow.className = "rounded-xl border border-slate-200 bg-slate-50 p-4 space-y-3";
  const stage = d.ebook_workflow_stage || "manuscript";
  const release = String(d.release_status || "—");
  const researchNotes = (d.research_notes || (d.fields && d.fields.research_notes) || d.pending_research || "").toString();
  const outline = Array.isArray(d.outline)
    ? d.outline
    : ((d.ebook_document && d.ebook_document.outline) || []);
  const visualPlan = d.visual_plan || {};
  const visualChapters = (visualPlan.chapters || []).length;
  const coverOk = !!(d.cover_design && (d.cover_design.local_generated || d.cover_design.image_path || d.cover_design.local_cover_pdf));
  workflow.innerHTML = `
    <h4 class="text-sm font-bold text-slate-900">Ebook Builder Workflow</h4>
    <p class="text-xs text-slate-500">Stage: <b>${escapeHtml(stage)}</b> · Release: <b data-ebook-release>${escapeHtml(release)}</b> · Export Ready: <b data-ebook-ready>${d.export_ready === true ? "yes" : "no"}</b></p>
    <label class="block text-xs font-semibold text-slate-700">Retained research
      <textarea data-ebook-research class="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" rows="3">${escapeHtml(researchNotes)}</textarea>
    </label>
    <div class="grid gap-3 md:grid-cols-2">
      <label class="block text-xs font-semibold text-slate-700">Title
        <input data-ebook-title class="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" value="${escapeHtml(d.title || "")}" />
      </label>
      <label class="block text-xs font-semibold text-slate-700">Subtitle
        <input data-ebook-subtitle class="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" value="${escapeHtml(d.subtitle || "")}" />
      </label>
    </div>
    <label class="block text-xs font-semibold text-slate-700">Outline (one chapter title per line)
      <textarea data-ebook-outline class="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm" rows="4">${escapeHtml(
        (outline.map ? outline.map(o => (o.title || o)).join("\n") : "") || ""
      )}</textarea>
    </label>
    <label class="block text-xs font-semibold text-slate-700">Chapter manuscript (Markdown)
      <textarea data-ebook-chapters class="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm font-mono" rows="8">${escapeHtml(d.content || d.ebook || "")}</textarea>
    </label>
    <div class="grid gap-3 md:grid-cols-3 text-xs">
      <div class="rounded-lg bg-white border border-slate-200 p-2">Visuals: <b>${visualChapters}</b> chapter slot group(s)</div>
      <label class="block font-semibold text-slate-700">Design theme
        <select data-ebook-theme class="mt-1 w-full rounded-lg border border-slate-300 p-2 text-sm">
          <option value="studio_clean"${(d.design_theme || "studio_clean") === "studio_clean" ? " selected" : ""}>Studio Clean</option>
          <option value="ink_editorial"${d.design_theme === "ink_editorial" ? " selected" : ""}>Ink Editorial</option>
        </select>
      </label>
      <div class="rounded-lg bg-white border border-slate-200 p-2">Cover: <b>${coverOk ? "local fixture present" : "missing"}</b>
        <button type="button" data-ebook-cover class="mt-2 btn-secondary text-xs">Use local cover fixture</button>
      </div>
    </div>
    <div class="flex flex-wrap gap-2">
      <button type="button" data-ebook-apply class="btn-secondary text-sm">Apply edits to draft</button>
      <button type="button" data-ebook-preflight class="btn-secondary text-sm">Run ebook preflight</button>
    </div>
    <pre data-ebook-preflight-out class="hidden text-xs bg-white border border-slate-200 rounded-lg p-3 overflow-auto max-h-48"></pre>
  `;
  wrap.appendChild(workflow);

  const syncFields = () => {
    d.research_notes = workflow.querySelector("[data-ebook-research]").value;
    d.title = workflow.querySelector("[data-ebook-title]").value.trim();
    d.subtitle = workflow.querySelector("[data-ebook-subtitle]").value.trim();
    d.content = workflow.querySelector("[data-ebook-chapters]").value;
    d.ebook = d.content;
    d.design_theme = workflow.querySelector("[data-ebook-theme]").value;
    d.fields = Object.assign({}, d.fields || {}, {
      subtitle: d.subtitle,
      design_theme: d.design_theme,
      research_notes: d.research_notes,
      author_brand: d.author_brand || (d.fields && d.fields.author_brand) || "Digital Product Factory",
    });
    const lines = workflow.querySelector("[data-ebook-outline]").value.split("\n").map(s => s.trim()).filter(Boolean);
    d.outline = lines.map((title, i) => ({ order: i + 1, title, approved: true }));
    d.ebook_workflow_stage = "edit_chapters";
  };
  workflow.querySelector("[data-ebook-apply]").onclick = () => {
    syncFields();
    // Editing invalidates any prior server PASS immediately.
    d.release_status = "";
    d.export_ready = false;
    d.release_certificate = null;
    d.release_report = null;
    const rel = workflow.querySelector("[data-ebook-release]");
    const ready = workflow.querySelector("[data-ebook-ready]");
    if (rel) rel.textContent = "—";
    if (ready) ready.textContent = "no";
    toast("Draft ebook fields updated (not approved). Prior release PASS cleared.");
  };
  workflow.querySelector("[data-ebook-cover]").onclick = () => {
    d.cover_design = Object.assign({}, d.cover_design || {}, {
      title: d.title || "EBOOK RECOVERY LOCAL FIXTURE — NOT FOR SALE",
      local_generated: true,
      fixture: true,
      local_cover_pdf: (d.cover_design && d.cover_design.local_cover_pdf) || "local_fixture",
    });
    d.release_status = "";
    d.export_ready = false;
    d.release_certificate = null;
    toast("Local cover fixture selected. Prior release PASS cleared.");
  };
  workflow.querySelector("[data-ebook-theme]").onchange = () => {
    syncFields();
    d.release_status = "";
    d.export_ready = false;
    d.release_certificate = null;
    const rel = workflow.querySelector("[data-ebook-release]");
    const ready = workflow.querySelector("[data-ebook-ready]");
    if (rel) rel.textContent = "—";
    if (ready) ready.textContent = "no";
  };
  workflow.querySelector("[data-ebook-preflight]").onclick = async () => {
    syncFields();
    const out = workflow.querySelector("[data-ebook-preflight-out]");
    out.classList.remove("hidden");
    out.textContent = "Running server ebook-release-check...";
    try {
      const draft = {
        title: d.title,
        subtitle: d.subtitle,
        content: d.content || d.ebook,
        ebook: d.content || d.ebook,
        outline: d.outline || [],
        design_theme: d.design_theme || "studio_clean",
        cover_design: d.cover_design || {},
        research_notes: d.research_notes || "",
        fields: d.fields || {},
        visual_plan: d.visual_plan || {},
        author_brand: d.author_brand || "Digital Product Factory",
      };
      const body = d._project_id != null
        ? { project_id: d._project_id, draft }
        : { draft, type: "ebook", name: d.title || "Ebook", data: Object.assign({}, d, draft, { product_type: "ebook" }) };
      // Prefer dedicated server release endpoint; never invent PASS locally.
      let report;
      try {
        report = await api("/ebook-release-check", {
          method: "POST",
          body: JSON.stringify(
            d._project_id != null
              ? { project_id: d._project_id, draft }
              : {
                  // Unsaved draft: send inline project payload via existing loader patterns.
                  project: {
                    id: null,
                    type: "ebook",
                    name: d.title || "Ebook",
                    data: Object.assign({}, d, draft, { product_type: "ebook" }),
                  },
                  draft,
                }
          ),
        });
      } catch (e) {
        // If unsaved project payload is rejected, surface the server error; do not set PASS.
        throw e;
      }
      d.release_status = report.release_status || "";
      d.export_ready = report.export_ready === true && String(report.release_status || "").toUpperCase() === "PASS";
      d.release_certificate = report.release_certificate || null;
      d.release_report = {
        status: report.release_status,
        blocking: report.blocking || [],
        issues: report.issues || [],
      };
      workflow.querySelector("[data-ebook-release]").textContent = d.release_status || "—";
      workflow.querySelector("[data-ebook-ready]").textContent = d.export_ready === true ? "yes" : "no";
      out.textContent = JSON.stringify(
        {
          release_status: d.release_status,
          export_ready: d.export_ready,
          issued_by: (d.release_certificate && d.release_certificate.issued_by) || null,
          blocking: report.blocking || [],
          issues: report.issues || [],
          identity: report.identity || null,
          note: "PASS/WARNING/FAIL are server-issued only. FAIL blocks Save-as-approved and PDF/ZIP.",
        },
        null,
        2
      );
    } catch (e) {
      d.release_status = "";
      d.export_ready = false;
      d.release_certificate = null;
      workflow.querySelector("[data-ebook-release]").textContent = "—";
      workflow.querySelector("[data-ebook-ready]").textContent = "no";
      out.textContent = String(e.message || e);
    }
  };

  // Pre-save: single "Save as Project" button.
  const preSave = document.createElement("div");
  preSave.className = "flex flex-wrap items-center justify-between gap-3";
  preSave.innerHTML = `<p class="text-sm text-slate-500">Save this ebook as a project to unlock downloads and selling options (only after release PASS).</p>`;
  const saveBtn = document.createElement("button");
  saveBtn.className = "btn-primary";
  saveBtn.textContent = "Save as Project";
  preSave.appendChild(saveBtn);
  wrap.appendChild(preSave);

  saveBtn.onclick = async () => {
    syncFields();
    const rs = String(d.release_status || "").toUpperCase();
    const certOk = d.release_certificate && d.release_certificate.issued_by === "server" && String(d.release_certificate.status || "").toUpperCase() === "PASS";
    if (rs === "FAIL" || (rs && rs !== "PASS") || d.export_ready === false || !certOk) {
      // Allow DRAFT project save, but block advertising approved/export-ready save.
      if (rs === "FAIL") {
        toast("Release FAIL — fix preflight issues before Save-as-approved / export.", "error");
        return;
      }
      if (rs !== "PASS" || !certOk) {
        toast("Run ebook preflight and obtain server PASS before Save-as-approved / downloads.", "error");
        // Still allow a plain draft save below only when user confirms? Brief says disable Save-as-approved.
        // Keep Save as Project for draft persistence, but strip export_ready.
        d.export_ready = false;
      }
    }
    const name = prompt("Name this project:", (d && d.title) || "Ebook") || "Ebook";
    if (!name) return;
    setBusyEl(saveBtn, true);
    try {
      const existingId = d && d._project_id != null ? d._project_id : null;
      const { _project_id, ...body } = d || {};
      body.product_type = "ebook";
      body.title = name;
      if (String(body.release_status || "").toUpperCase() !== "PASS" || !(body.release_certificate && body.release_certificate.issued_by === "server")) {
        body.export_ready = false;
      }
      markUserSaved(body);
      const saved = existingId != null
        ? await api(`/projects/${existingId}`, { method: "PUT", body: JSON.stringify({ name, type: "ebook", data: body }) })
        : await api("/projects", { method: "POST", body: JSON.stringify({ name, type: "ebook", data: body }) });
      if (saved && saved.id != null) d._project_id = saved.id;
      loadProjects();
      toast(existingId != null ? "Project updated" : "Project saved");
      preSave.remove();
      wrap.appendChild(postEbookNextSteps(d, saved.id, name));
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusyEl(saveBtn, false);
    }
  };

  return wrap;
}

// Post-Save Next Steps panel for ebooks. Shown right under the ebook content
// after a successful save. Only shows working, wired options. The PDF / ZIP
// / package buttons auto-call /export-product on first click so the user
// doesn't have to navigate away to download.
async function postEbookNextSteps(d, projectId, name) {
  const wrap = document.createElement("div");
  wrap.className = "space-y-5";

  const head = document.createElement("div");
  head.innerHTML = card(
    `<span class="inline-flex items-center gap-2 rounded-full bg-emerald-600 text-white text-xs font-semibold px-3 py-1 mb-2">Project completed: Ebook</span>
     <h3 class="text-lg font-bold text-slate-900">${escapeHtml(name)}</h3>
     <p class="text-sm text-slate-500 mt-1">Project #${projectId}. Download your finished ebook, or prepare a marketplace listing.</p>`
  );
  wrap.appendChild(head);

  const primary = document.createElement("div");
  primary.innerHTML = card(
    `<h4 class="text-sm font-bold text-slate-900 mb-3">Primary</h4>
     <div class="flex flex-wrap gap-3">
       <button data-pri="pdf" class="${NS_BTN}">Download PDF</button>
       <button data-pri="zip" class="${NS_BTN}">Download ZIP</button>
       <button data-pri="cover" class="${NS_BTN} border-indigo-300 text-indigo-700 hover:bg-indigo-50">Edit Cover</button>
       <button data-pri="open" class="${NS_BTN}">Open Product</button>
     </div>
     <p data-pri-msg class="hidden mt-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2"></p>`
  );
  wrap.appendChild(primary);

  const selling = document.createElement("div");
  selling.innerHTML = card(
    `<h4 class="text-sm font-bold text-slate-900 mb-3">Selling / Publishing</h4>
     <p class="text-xs text-slate-500 mb-3">Each option generates a marketplace-ready package on demand.</p>
     <div class="flex flex-wrap gap-3">
       <button data-sell="kdp" class="${NS_BTN}">Create KDP Package</button>
       <button data-sell="etsy" class="${NS_BTN}">Create Etsy Package</button>
       <button data-sell="gumroad" class="${NS_BTN}">Create Gumroad Package</button>
       <button data-sell="lemon_squeezy" class="${NS_BTN}">Create Lemon Squeezy Package</button>
       <button data-sell="sales" class="${NS_BTN}">Generate Sales Page</button>
       <button data-sell="ad" class="${NS_BTN}">Generate Ad Script</button>
     </div>
     <div class="mt-3 pt-3 border-t border-slate-200">
       <p class="text-xs font-semibold text-slate-700 mb-2">Traffic / Funnel</p>
       <div class="flex flex-wrap gap-3">
         <button id="createTrafficContentBtn" class="${NS_BTN} border-brand-300 text-brand-700 hover:bg-brand-50">Create Traffic Content</button>
         <button id="createLaunchPkgBtn" class="${NS_BTN} border-amber-300 text-amber-700 hover:bg-amber-50">Create Launch Package</button>
       </div>
     </div>
     <div data-kdp-preflight-slot class="mt-4 pt-3 border-t border-slate-200"></div>
     <div data-sell-result class="mt-4"></div>`
  );
  wrap.appendChild(selling);
  const ebookKdpSlot = selling.querySelector("[data-kdp-preflight-slot]");
  if (ebookKdpSlot) ebookKdpSlot.appendChild(kdpPreflightPanel(d, projectId));

  // Wire Create Traffic Content button — prefill from the ebook's plan data
  const tcBtn = selling.querySelector("#createTrafficContentBtn");
  if (tcBtn) {
    tcBtn.onclick = () => {
      const ctx = {
        product_title: d.title || "",
        product_type: d.product_type || "ebook",
        target_audience: (d.plan && d.plan.target_audience) || d.target_audience || "",
        customer_problem: (d.plan && d.plan.customer_problem) || "",
        product_promise: (d.plan && d.plan.product_promise) || "",
        freebie_name: (d.plan && d.plan.freebie_name) || d.freebie_name || "",
        landing_page_url: (d.plan && d.plan.landing_page_url) || d.landing_page_url || "",
        tone: (d.plan && d.plan.tone) || d.tone || "helpful and relatable",
      };
      goAdGenerator(ctx);
    };
  }

  // Wire Create Launch Package button
  const lpBtn = selling.querySelector("#createLaunchPkgBtn");
  if (lpBtn) {
    lpBtn.onclick = () => renderLaunchPackage(projectId, d);
  }

  const msg = primary.querySelector("[data-pri-msg]");
  const sellResult = selling.querySelector("[data-sell-result]");

  // -- Primary: Download PDF / Download ZIP / Open Product
  async function runExport() {
    const rs = String(d.release_status || "").toUpperCase();
    const cert = d.release_certificate;
    const certOk = cert && cert.issued_by === "server" && String(cert.status || "").toUpperCase() === "PASS";
    if (rs !== "PASS" || d.export_ready !== true || !certOk) {
      throw new Error(
        "Ebook release is not server PASS — Export Ready/downloads are blocked. Run ebook preflight first."
      );
    }
    // Use the persisted exports if available, otherwise call /export-product.
    if (d.product_exports && d.product_exports.files && d.export_ready === true) return d.product_exports;
    const r = await api("/export-product", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId }),
    });
    d.product_exports = r.exports;
    d.export_package_id = r.package_id;
    if (r && r.release_status) d.release_status = r.release_status;
    if (r && r.release_certificate) d.release_certificate = r.release_certificate;
    if (r && typeof r.export_ready === "boolean") d.export_ready = r.export_ready;
    if (r && r.exports) {
      // Refresh release flags from server-persisted project if present later.
      d.export_ready = d.export_ready !== false;
    }
    return r.exports;
  }
  function showMsg(text) { msg.textContent = text; msg.classList.remove("hidden"); }

  primary.querySelector('[data-pri="pdf"]').onclick = async (e) => {
    const b = e.currentTarget;
    setBusyEl(b, true);
    try {
      const ex = await runExport();
      const f = (ex && ex.files && ex.files.pdf) || null;
      if (f && f.url) {
        await triggerDownload(f.url, f.name || (name + ".pdf"));
        showMsg("PDF download started.");
      } else {
        showMsg("PDF is not available for this project yet. Try Export again or refresh.");
      }
    } catch (err) { showMsg("Could not prepare PDF: " + err.message); }
    finally { setBusyEl(b, false); }
  };
  const coverPri = primary.querySelector('[data-pri="cover"]');
  if (coverPri) {
    coverPri.onclick = () => {
      d._project_id = projectId;
      d.product_type = d.product_type || "ebook";
      openCoverEditor(d);
    };
  }
  primary.querySelector('[data-pri="zip"]').onclick = async (e) => {
    const b = e.currentTarget;
    setBusyEl(b, true);
    try {
      const ex = await runExport();
      const f = (ex && ex.files && ex.files.zip) || null;
      if (f && f.url) {
        await triggerDownload(f.url, f.name || (name + ".zip"));
        showMsg("ZIP download started.");
      } else {
        showMsg("ZIP is not available for this project yet. Try Export again or refresh.");
      }
    } catch (err) { showMsg("Could not prepare ZIP: " + err.message); }
    finally { setBusyEl(b, false); }
  };
  primary.querySelector('[data-pri="open"]').onclick = () => {
    // "Open Product" = jump to the saved project in the Saved Projects list
    // so the user can reopen it, edit, or continue the workflow.
    go("saved");
    toast("Project #" + projectId + " is now in Saved Projects.");
  };

  // -- Selling: KDP / Etsy / Gumroad / Lemon Squeezy / Sales Page / Ad Script
  const handlers = {
    kdp: { fn: () => api("/generate-seller-package", { method: "POST", body: JSON.stringify({ project_id: projectId, platform: "kdp" }) }), label: "Amazon KDP" },
    etsy: { fn: () => api("/generate-seller-package", { method: "POST", body: JSON.stringify({ project_id: projectId, platform: "etsy" }) }), label: "Etsy" },
    gumroad: { fn: () => api("/generate-seller-package", { method: "POST", body: JSON.stringify({ project_id: projectId, platform: "gumroad" }) }), label: "Gumroad" },
    lemon_squeezy: { fn: () => api("/generate-seller-package", { method: "POST", body: JSON.stringify({ project_id: projectId, platform: "lemon_squeezy" }) }), label: "Lemon Squeezy" },
    sales: { fn: () => api("/generate-sales-page", { method: "POST", body: JSON.stringify({ project_id: projectId }) }), label: "Sales Page" },
    ad: { fn: () => api("/generate-product-ad", { method: "POST", body: JSON.stringify({ project_id: projectId }) }), label: "Video Ad Scripts" },
  };
  Object.entries(handlers).forEach(([key, h]) => {
    const btn = selling.querySelector(`[data-sell="${key}"]`);
    if (!btn) return;
    btn.onclick = async () => {
      setBusyEl(btn, true);
      sellResult.innerHTML = spinner("Building your " + h.label + " package...");
      try {
        const r = await h.fn();
        // Seller packages return {platform, package}; sales/ad return their own shape.
        const payload = (r && r.package) ? r.package : r;
        sellResult.innerHTML = card(
          `<h4 class="text-base font-bold text-slate-900 mb-2">${escapeHtml(h.label)}</h4>` +
          packageResultHtml(payload)
        );
      } catch (e) {
        sellResult.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
      } finally {
        setBusyEl(btn, false);
      }
    };
  });

  return wrap;
}

async function triggerDownload(url, name) {
  // Fetch first so download-gate 403/400 JSON is toasted instead of looking like
  // a dead button (browser would otherwise "download" an error payload).
  try {
    const resp = await fetch(url, { credentials: "same-origin" });
    const ct = (resp.headers.get("content-type") || "").toLowerCase();
    if (!resp.ok || ct.includes("application/json")) {
      let msg = "Download failed (" + resp.status + ").";
      try {
        const j = await resp.clone().json();
        if (j && j.message) msg = j.message;
        else if (j && j.error) msg = String(j.error);
      } catch (_) {
        /* keep status message */
      }
      throw new Error(msg);
    }
    const blob = await resp.blob();
    const objUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objUrl;
    if (name) a.download = name;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(objUrl), 2000);
  } catch (err) {
    // Fall back to direct navigation only for network failures after a OK was
    // impossible to confirm; still surface the message to callers via throw.
    if (err && err.message) throw err;
    const a = document.createElement("a");
    a.href = url;
    if (name) a.download = name;
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
}

function packageResultHtml(payload) {
  if (!payload || typeof payload !== "object") return `<p class="text-sm text-slate-500">No content.</p>`;
  // Ad scripts shape: {ad_30, ad_60}
  if (payload.ad_30 || payload.ad_60) {
    return `<h5 class="text-sm font-semibold text-slate-800 mb-1">30-Second Script</h5>
            <div class="prose-out mb-4 text-sm">${md(payload.ad_30 || "")}</div>
            <h5 class="text-sm font-semibold text-slate-800 mb-1">60-Second Script</h5>
            <div class="prose-out text-sm">${md(payload.ad_60 || "")}</div>`;
  }
  // Sales page shape: {sales_page}
  if (payload.sales_page) {
    return `<div class="prose-out text-sm">${md(payload.sales_page)}</div>`;
  }
  // Generic seller package: list of humanized fields.
  const skip = new Set(["platform", "platform_label"]);
  const rows = Object.entries(payload).filter(([k]) => !skip.has(k)).map(([k, v]) => {
    let body;
    if (Array.isArray(v)) {
      body = v.length
        ? `<ul class="list-disc pl-5 text-sm text-slate-600 space-y-0.5">${v.map((it) => `<li>${escapeHtml(typeof it === "string" ? it : JSON.stringify(it))}</li>`).join("")}</ul>`
        : `<p class="text-sm text-slate-400">—</p>`;
    } else {
      body = `<p class="text-sm text-slate-600 whitespace-pre-wrap">${escapeHtml(v || "—")}</p>`;
    }
    return `<div><h5 class="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">${escapeHtml(humanizeKey(k))}</h5>${body}</div>`;
  }).join("");
  return `<div class="grid sm:grid-cols-2 gap-4">${rows}</div>`;
}

// ---------- Ebook Project workspace (stage rail) ----------
let _ebookWorkspaceState = null;

function _ebookRailStatusClass(status) {
  switch (String(status || "")) {
    case "approved": return "bg-emerald-100 text-emerald-800 border-emerald-200";
    case "awaiting_approval": return "bg-amber-100 text-amber-800 border-amber-200";
    case "in_progress": return "bg-sky-100 text-sky-800 border-sky-200";
    case "needs_correction": return "bg-orange-100 text-orange-800 border-orange-200";
    case "blocked": return "bg-rose-100 text-rose-800 border-rose-200";
    default: return "bg-slate-100 text-slate-600 border-slate-200";
  }
}

async function startEbookWorkspaceFromBuilder() {
  const topic = (document.getElementById("ebookInput").value || "").trim();
  const author = (document.getElementById("ebookAuthor").value || "").trim();
  if (!topic) return toast("Enter a topic to start the Ebook Project workspace.", "error");
  if (!author) return toast("Enter an author name.", "error");
  try {
    const created = await api("/ebook-workspace", {
      method: "POST",
      body: JSON.stringify({
        topic,
        author,
        audience: "",
        outcome: "",
        name: topic.slice(0, 120),
      }),
    });
    toast("Ebook Project workspace created at Research.");
    loadProjects();
    await openEbookWorkspace(created.project.id);
  } catch (e) {
    toast(e.message || String(e), "error");
  }
}

async function openEbookWorkspace(projectId) {
  go("ebook-workspace");
  const root = document.getElementById("ebookWorkspaceRoot");
  if (!root) return;
  root.innerHTML = spinner("Opening Ebook Project workspace...");
  try {
    const res = await api(`/ebook-workspace/${projectId}`);
    _ebookWorkspaceState = res.workspace;
    renderEbookWorkspace(res.workspace);
  } catch (e) {
    root.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message || String(e))}</p>`);
  }
}

function renderEbookWorkspace(ws) {
  _ebookWorkspaceState = ws;
  const root = document.getElementById("ebookWorkspaceRoot");
  if (!root) return;
  const budget = ws.budget || {};
  const railHtml = (ws.rail || []).map((s) => {
    const active = s.id === ws.current_stage;
    return `<button type="button" data-ws-stage="${escapeHtml(s.id)}"
      class="ebook-rail-item flex flex-col items-start gap-1 rounded-xl border px-3 py-2 text-left min-w-[7.5rem] ${
        active ? "ring-2 ring-brand-400 border-brand-300 bg-white" : "bg-white/80"
      } ${_ebookRailStatusClass(s.status)}">
      <span class="text-[11px] font-bold uppercase tracking-wide opacity-80">${escapeHtml(s.label)}</span>
      <span class="text-xs font-semibold">${escapeHtml(s.status_label || s.status)}</span>
    </button>`;
  }).join("");

  root.innerHTML = `
    <div class="rounded-2xl border border-slate-200 bg-white p-6 space-y-4" data-ebook-workspace>
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="min-w-0">
          <p class="text-xs font-semibold uppercase tracking-wide text-brand-600">Ebook Project</p>
          <h2 class="text-xl font-bold text-slate-900 truncate">${escapeHtml(ws.name || ws.title || "Ebook")}</h2>
          <p class="text-sm text-slate-500 mt-1">Author: <b>${escapeHtml(ws.author || "—")}</b>
            · Artifact: <b>${escapeHtml(ws.artifact_state || "DRAFT")}</b>
            · Rev ${escapeHtml(String(ws.artifact_revision || 1))}</p>
        </div>
        <div class="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
          <div>Spend: <b>$${Number(budget.spent_usd || 0).toFixed(3)}</b></div>
          <div>Remaining: <b>$${Number(budget.remaining_usd || 0).toFixed(3)}</b></div>
          <div class="text-xs text-slate-500">Cap $${Number(budget.cap_usd || 0).toFixed(2)} · ${Number(budget.paid_calls || 0)} paid calls</div>
        </div>
      </div>
      <div class="flex gap-2 overflow-x-auto pb-1" data-ebook-rail>${railHtml}</div>
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-sm text-slate-600">Next production action:</span>
        <b class="text-sm text-slate-900" data-ws-next-label>${escapeHtml(ws.next_action_label || ws.next_action || "—")}</b>
        ${
          ws.next_action === "generate_manuscript" && ws.gates && ws.gates.manuscript_enabled
            ? `<button type="button" class="btn-primary text-sm" data-ws-estimate-manuscript>Generate Manuscript…</button>`
            : (ws.next_action === "request_correction" || ws.next_action === "correct_manuscript") && ws.gates && ws.gates.correction_enabled
            ? `<button type="button" class="btn-primary text-sm" data-ws-request-correction-top>Request Correction…</button>`
            : `<button type="button" class="btn-secondary text-sm opacity-60 cursor-not-allowed" disabled title="Blocked until prior stages are approved">Generate Manuscript</button>`
        }
      </div>
      <div data-ws-stage-panel class="rounded-xl border border-slate-200 bg-slate-50 p-4"></div>
      <div data-ws-confirm class="hidden rounded-xl border border-amber-300 bg-amber-50 p-4 space-y-3"></div>
    </div>
  `;

  root.querySelectorAll("[data-ws-stage]").forEach((btn) => {
    btn.onclick = () => showEbookWorkspaceStage(btn.getAttribute("data-ws-stage"));
  });
  const estBtn = root.querySelector("[data-ws-estimate-manuscript]");
  if (estBtn) {
    estBtn.onclick = () => estimateManuscriptInWorkspace(ws.project_id);
  }
  const corrTop = root.querySelector("[data-ws-request-correction-top]");
  if (corrTop) {
    corrTop.onclick = () => estimateCorrectionInWorkspace(ws.project_id);
  }
  showEbookWorkspaceStage(ws.current_stage || "research");
}

function showEbookWorkspaceStage(stageId) {
  const ws = _ebookWorkspaceState;
  if (!ws) return;
  const panel = document.querySelector("[data-ws-stage-panel]");
  if (!panel) return;
  const stage = (ws.rail || []).find((s) => s.id === stageId) || { id: stageId, label: stageId, status_label: "" };
  let body = "";
  if (stageId === "research") {
    const r = ws.research || {};
    const findings = (r.key_findings || []).map((f) => `<li>${escapeHtml(f)}</li>`).join("") || "<li class=\"text-slate-400\">None yet</li>";
    const sources = (r.source_urls || []).slice(0, 12).map((u) => `<li class="truncate"><a class="text-brand-700 underline" href="${escapeHtml(u)}" target="_blank" rel="noopener">${escapeHtml(u)}</a></li>`).join("") || "<li class=\"text-slate-400\">—</li>";
    const rules = (ws.editorial_rules_locked || []).map((x) => `<li>${escapeHtml(x)}</li>`).join("") || "<li class=\"text-slate-400\">—</li>";
    body = `
      <h3 class="text-sm font-bold text-slate-900 mb-2">Research · ${escapeHtml(stage.status_label || "")}</h3>
      <p class="text-sm text-slate-700 whitespace-pre-wrap mb-3">${escapeHtml(r.summary || "")}</p>
      <h4 class="text-xs font-semibold uppercase text-slate-500 mb-1">Key findings</h4>
      <ul class="list-disc pl-5 text-sm text-slate-700 space-y-1 mb-3">${findings}</ul>
      <h4 class="text-xs font-semibold uppercase text-slate-500 mb-1">Printing notes</h4>
      <p class="text-sm text-slate-700 mb-2">${escapeHtml((r.printing_research && r.printing_research.keepsake_notes) || "")}</p>
      <p class="text-xs text-slate-500 mb-3">Evidence: ${escapeHtml((r.printing_research && r.printing_research.evidence_quality) || "—")}</p>
      <h4 class="text-xs font-semibold uppercase text-slate-500 mb-1">Locked editorial rules</h4>
      <ul class="list-disc pl-5 text-sm text-slate-700 space-y-1 mb-3">${rules}</ul>
      <h4 class="text-xs font-semibold uppercase text-slate-500 mb-1">Sources</h4>
      <ul class="text-sm space-y-1">${sources}</ul>
    `;
  } else if (stageId === "title") {
    body = `
      <h3 class="text-sm font-bold text-slate-900 mb-2">Title · ${escapeHtml(stage.status_label || "")}</h3>
      <p class="text-lg font-semibold text-slate-900">${escapeHtml(ws.title || "—")}</p>
      <p class="text-sm text-slate-600 mt-1">${escapeHtml(ws.subtitle || "")}</p>
      <p class="text-xs text-slate-500 mt-3">Approved option: ${escapeHtml(ws.approved_title_id || "—")}</p>
    `;
  } else if (stageId === "outline") {
    const chapters = (ws.outline || []).map((c) => `
      <li class="rounded-lg border border-slate-200 bg-white p-3">
        <div class="font-semibold text-slate-900">Chapter ${escapeHtml(String(c.order || ""))}: ${escapeHtml(c.title || "")}</div>
        <pre class="mt-1 text-xs text-slate-600 whitespace-pre-wrap font-sans">${escapeHtml(c.purpose || "")}</pre>
      </li>`).join("") || `<li class="text-slate-400 text-sm">No outline yet</li>`;
    body = `
      <h3 class="text-sm font-bold text-slate-900 mb-2">Outline · ${escapeHtml(stage.status_label || "")}</h3>
      <p class="text-xs text-slate-500 mb-3">Approved option: ${escapeHtml(ws.approved_outline_id || "—")}</p>
      <ol class="space-y-2">${chapters}</ol>
    `;
  } else if (stageId === "manuscript") {
    const m = ws.manuscript || {};
    const findings = (m.chapter_findings || []).flatMap((ch) =>
      (ch.findings || []).map((f) => `<li><b>Ch ${escapeHtml(String(ch.order || ""))} ${escapeHtml(ch.title || "")}:</b> ${escapeHtml(String(f.code || ""))} — ${escapeHtml(String(f.message || f))}</li>`)
    ).join("") || (m.structure_findings || m.qa_findings || []).map((f) => `<li>${escapeHtml(String(f))}</li>`).join("");
    const chapters = (m.chapters || []).map((c) =>
      `<li class="rounded-lg border border-slate-200 bg-white p-2 text-sm"><b>Ch ${escapeHtml(String(c.order || ""))}:</b> ${escapeHtml(c.title || "")}${c.quality_status ? ` · ${escapeHtml(String(c.quality_status))}` : ""}${c.word_count != null ? ` · ${escapeHtml(String(c.word_count))} words` : ""}</li>`
    ).join("");
    const canApprove = m.can_approve === true && m.status === "awaiting_approval" && m.quality_status === "PASS";
    const needsCorrection = m.status === "needs_correction";
    const contentPreview = (m.content || "").slice(0, 4000);
    const rem = Number((m.remaining_usd != null ? m.remaining_usd : (ws.budget || {}).remaining_usd) || 0);
    const corrEst = Number(m.correction_estimate_usd || 0.75);
    body = `
      <h3 class="text-sm font-bold text-slate-900 mb-2">Manuscript · ${escapeHtml(stage.status_label || m.status_label || "")}</h3>
      ${
        m.status === "not_started"
          ? `<p class="text-sm text-slate-600">Not started. Click <b>Generate Manuscript…</b> for a cost estimate. Nothing is spent until you click <b>Confirm and Generate Manuscript</b>.</p>`
          : ""
      }
      ${
        needsCorrection
          ? `<p class="text-sm text-orange-800 mb-2">Needs correction. The generated draft is preserved for inspection. Approve is blocked while structural FAIL findings remain.</p>`
          : ""
      }
      ${
        m.quality_status
          ? `<p class="text-sm mb-2 ${m.quality_status === "PASS" ? "text-emerald-800" : "text-rose-800"}">Quality: <b>${escapeHtml(m.quality_status)}</b>${m.quality_status !== "PASS" ? " — Approve Manuscript is disabled until quality is PASS." : ""}</p>`
          : ""
      }
      ${chapters ? `<h4 class="text-xs font-semibold uppercase text-slate-500 mb-1">Generated chapter list</h4><ol class="space-y-1 mb-3">${chapters}</ol>` : ""}
      ${findings ? `<h4 class="text-xs font-semibold uppercase text-rose-700 mb-1">Chapter-level / QA findings</h4><ul class="list-disc pl-5 text-sm text-rose-700 mb-3">${findings}</ul>` : ""}
      ${contentPreview ? `<h4 class="text-xs font-semibold uppercase text-slate-500 mb-1">Preserved draft (preview)</h4><pre class="text-xs bg-white border border-slate-200 rounded-lg p-3 whitespace-pre-wrap max-h-64 overflow-auto font-mono">${escapeHtml(contentPreview)}</pre>` : ""}
      ${
        canApprove
          ? `<div class="mt-3 flex flex-wrap gap-2">
              <button type="button" class="btn-primary text-sm" data-ws-approve-manuscript>Approve Manuscript</button>
            </div>`
          : ""
      }
      ${
        needsCorrection
          ? `<div class="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 space-y-2">
              <p class="text-sm text-amber-900">Request Correction first issues a <b>free $0 estimate</b>. Nothing is spent until you check authorization and click <b>Confirm and Correct Manuscript</b>.</p>
              <p class="text-xs text-amber-800">Remaining project budget: <b>$${rem.toFixed(3)}</b>. Estimated maximum remaining work if confirmed: <b>$${corrEst.toFixed(3)}</b>. Correction uses the existing manuscript and the exact approved outline — it does not restart research.</p>
              <button type="button" class="btn-primary text-sm" data-ws-request-correction>Request Correction…</button>
            </div>`
          : ""
      }
    `;
  } else if (stageId === "visuals") {
    const d = ws.design || {};
    const slots = ((d.visual_manifest || {}).slots || []).map((s) =>
      `<li class="text-sm">Ch ${escapeHtml(String(s.chapter || ""))}: ${escapeHtml(s.title || "")} · ${(s.kinds || []).map((k) => escapeHtml(k)).join(", ")}</li>`
    ).join("") || `<li class="text-sm text-slate-500">Manuscript tables, checklists, and workflows become designed components. No paid images in this pass.</li>`;
    body = `
      <h3 class="text-sm font-bold text-slate-900 mb-2">Visuals · ${escapeHtml(stage.status_label || "")}</h3>
      <p class="text-sm text-slate-600 mb-3">Optional approved visuals are manuscript-derived. This stage never calls an image API.</p>
      <ul class="list-disc pl-5 mb-3 space-y-1">${slots}</ul>
      ${
        ws.gates && ws.gates.visuals_enabled && stage.status !== "approved"
          ? `<button type="button" class="btn-primary text-sm" data-ws-approve-visuals>Approve manuscript-derived visuals</button>`
          : `<p class="text-xs text-slate-500">Server status: ${escapeHtml(stage.status_label || stage.status || "")}</p>`
      }
    `;
  } else if (stageId === "cover") {
    const c = (ws.design || {}).cover || {};
    body = `
      <h3 class="text-sm font-bold text-slate-900 mb-2">Cover · ${escapeHtml(stage.status_label || "")}</h3>
      <p class="text-sm text-slate-700"><b>${escapeHtml(c.title || ws.title || "")}</b></p>
      <p class="text-sm text-slate-600">${escapeHtml(c.subtitle || ws.subtitle || "")}</p>
      <p class="text-sm text-slate-600 mb-2">Author: ${escapeHtml(c.author || ws.author || "")}</p>
      <p class="text-xs text-slate-500 mb-3">Theme: ${escapeHtml(c.theme || "—")} · Digest: ${escapeHtml((c.digest || "").slice(0, 16) || "—")}</p>
      <div class="flex flex-wrap gap-2">
        ${ws.gates && ws.gates.cover_enabled ? `<button type="button" class="btn-secondary text-sm" data-ws-generate-cover>Generate local cover</button>` : ""}
        ${c.digest && stage.status !== "approved" ? `<button type="button" class="btn-primary text-sm" data-ws-approve-cover>Approve cover</button><button type="button" class="btn-secondary text-sm" data-ws-reject-cover>Reject cover</button>` : ""}
      </div>
    `;
  } else if (stageId === "design") {
    const d = ws.design || {};
    const themes = (d.themes || []).map((t) => `
      <button type="button" class="rounded-xl border p-3 text-left ${d.selected_theme === t.theme_id ? "border-brand-400 ring-2 ring-brand-300" : "border-slate-200"}" data-ws-select-theme="${escapeHtml(t.theme_id)}">
        <div class="font-semibold text-slate-900">${escapeHtml(t.display_name)}</div>
        <p class="text-xs text-slate-600 mt-1">${escapeHtml(t.summary || "")}</p>
      </button>`).join("");
    body = `
      <h3 class="text-sm font-bold text-slate-900 mb-2">Design · ${escapeHtml(stage.status_label || "")}</h3>
      <p class="text-sm text-slate-600 mb-3">Preview and select a professional theme. Theme changes do not rewrite the manuscript. No paid calls.</p>
      <div class="grid gap-2 sm:grid-cols-3 mb-3">${themes || "<p class='text-sm text-slate-500'>Themes unlock after cover approval.</p>"}</div>
      <p class="text-xs text-slate-500 mb-3">Selected: ${escapeHtml(d.selected_theme || "—")} · Design digest: ${escapeHtml((d.design_digest || "").slice(0, 16) || "—")}</p>
      ${d.selected_theme && stage.status !== "approved" ? `<button type="button" class="btn-primary text-sm" data-ws-approve-design>Approve design</button>` : ""}
    `;
  } else if (stageId === "preview") {
    const d = ws.design || {};
    body = `
      <h3 class="text-sm font-bold text-slate-900 mb-2">Preview · ${escapeHtml(stage.status_label || "")}</h3>
      <p class="text-sm text-slate-600 mb-3">Preview identity is bound to the same manuscript, design, and cover digests as PDF/ZIP.</p>
      ${d.preview_available ? `<p class="text-xs text-emerald-800 mb-2">Preview HTML is stored on the server.</p>` : `<p class="text-xs text-slate-500 mb-2">Build preview to inspect every designed page.</p>`}
      <div class="flex flex-wrap gap-2">
        ${ws.gates && ws.gates.preview_enabled ? `<button type="button" class="btn-secondary text-sm" data-ws-build-preview>Build preview</button>` : ""}
        ${d.preview_available && stage.status !== "approved" ? `<button type="button" class="btn-primary text-sm" data-ws-approve-preview>Approve preview</button>` : ""}
      </div>
    `;
  } else if (stageId === "preflight") {
    const pre = (ws.design || {}).preflight || {};
    const findings = (pre.findings || []).map((f) => `<li class="text-sm">${escapeHtml(String(f.code || ""))}: ${escapeHtml(String(f.message || f))}</li>`).join("");
    const status = pre.status || "not run";
    body = `
      <h3 class="text-sm font-bold text-slate-900 mb-2">Preflight · ${escapeHtml(stage.status_label || "")}</h3>
      <p class="text-sm mb-2">Server status: <b class="${status === "PASS" ? "text-emerald-800" : "text-rose-800"}">${escapeHtml(status)}</b>. The UI cannot invent PASS or Export Ready.</p>
      ${findings ? `<ul class="list-disc pl-5 mb-3 text-rose-800">${findings}</ul>` : `<p class="text-sm text-slate-600 mb-3">No findings yet, or preflight has not been run.</p>`}
      <div class="flex flex-wrap gap-2">
        ${ws.gates && ws.gates.preflight_enabled ? `<button type="button" class="btn-secondary text-sm" data-ws-run-preflight>Run preflight</button>` : ""}
        ${status === "PASS" && stage.status !== "approved" ? `<button type="button" class="btn-primary text-sm" data-ws-approve-preflight>Approve preflight</button>` : ""}
      </div>
    `;
  } else if (stageId === "export") {
    const ready = !!(ws.gates && ws.gates.export_enabled);
    const ident = (ws.design || {}).identity || {};
    body = `
      <h3 class="text-sm font-bold text-slate-900 mb-2">Export · ${escapeHtml(stage.status_label || "")}</h3>
      <p class="text-sm mb-2">${ready ? "Export Ready on the server. Preview, PDF, and ZIP share the same identity." : "Export is blocked until manuscript quality and design preflight both PASS on the server."}</p>
      <p class="text-xs text-slate-500 mb-3">PDF ${escapeHtml((ident.pdf_sha256 || "").slice(0, 16) || "—")} · ZIP ${escapeHtml((ident.zip_sha256 || "").slice(0, 16) || "—")}</p>
      ${ready ? `<p class="text-sm text-emerald-800">Download uses the saved project export buttons. This panel does not forge Export Ready.</p>` : `<button type="button" class="btn-secondary text-sm opacity-60 cursor-not-allowed" disabled>Export blocked</button>`}
    `;
  } else {
    body = `
      <h3 class="text-sm font-bold text-slate-900 mb-2">${escapeHtml(stage.label || stageId)} · ${escapeHtml(stage.status_label || "Not started")}</h3>
      <p class="text-sm text-slate-600">This stage unlocks after earlier approvals. Server state controls availability — the UI cannot invent PASS or approvals.</p>
    `;
  }
  panel.innerHTML = body;
  const approveBtn = panel.querySelector("[data-ws-approve-manuscript]");
  if (approveBtn) {
    approveBtn.onclick = async () => {
      try {
        const res = await api(`/ebook-workspace/${ws.project_id}/approve`, {
          method: "POST",
          body: JSON.stringify({ stage: "manuscript" }),
        });
        renderEbookWorkspace(res.workspace);
        toast("Manuscript approved.");
      } catch (e) {
        toast(e.message || String(e), "error");
      }
    };
  }
  const corrBtn = panel.querySelector("[data-ws-request-correction]");
  if (corrBtn) {
    corrBtn.onclick = () => estimateCorrectionInWorkspace(ws.project_id);
  }
  const bind = (sel, fn) => {
    const el = panel.querySelector(sel);
    if (el) el.onclick = fn;
  };
  bind("[data-ws-approve-visuals]", () => postEbookWorkspaceAction(`/ebook-workspace/${ws.project_id}/visuals`, {}, "Visuals approved."));
  bind("[data-ws-generate-cover]", () => postEbookWorkspaceAction(`/ebook-workspace/${ws.project_id}/cover`, { action: "generate" }, "Local cover generated."));
  bind("[data-ws-reject-cover]", () => postEbookWorkspaceAction(`/ebook-workspace/${ws.project_id}/cover`, { action: "reject" }, "Cover rejected."));
  bind("[data-ws-approve-cover]", () => postEbookWorkspaceAction(`/ebook-workspace/${ws.project_id}/approve`, { stage: "cover" }, "Cover approved."));
  panel.querySelectorAll("[data-ws-select-theme]").forEach((btn) => {
    btn.onclick = () => postEbookWorkspaceAction(
      `/ebook-workspace/${ws.project_id}/design`,
      { theme_id: btn.getAttribute("data-ws-select-theme") },
      "Theme selected."
    );
  });
  bind("[data-ws-approve-design]", () => postEbookWorkspaceAction(`/ebook-workspace/${ws.project_id}/approve`, { stage: "design" }, "Design approved."));
  bind("[data-ws-build-preview]", () => postEbookWorkspaceAction(`/ebook-workspace/${ws.project_id}/preview`, {}, "Preview built."));
  bind("[data-ws-approve-preview]", () => postEbookWorkspaceAction(`/ebook-workspace/${ws.project_id}/approve`, { stage: "preview" }, "Preview approved."));
  bind("[data-ws-run-preflight]", () => postEbookWorkspaceAction(`/ebook-workspace/${ws.project_id}/preflight`, {}, "Preflight finished."));
  bind("[data-ws-approve-preflight]", () => postEbookWorkspaceAction(`/ebook-workspace/${ws.project_id}/approve`, { stage: "preflight" }, "Preflight approved."));
}

async function postEbookWorkspaceAction(url, body, okMessage) {
  try {
    const res = await api(url, { method: "POST", body: JSON.stringify(body || {}) });
    if (res.workspace) renderEbookWorkspace(res.workspace);
    if (okMessage) toast(okMessage);
  } catch (e) {
    toast(e.message || String(e), "error");
  }
}

async function estimateCorrectionInWorkspace(projectId) {
  const confirmEl = document.querySelector("[data-ws-confirm]");
  if (!confirmEl) return;
  confirmEl.classList.remove("hidden");
  confirmEl.innerHTML = `<p class="text-sm text-slate-700">Preparing correction cost estimate…</p>`;
  try {
    const res = await api(`/ebook-workspace/${projectId}/estimate-cost`, {
      method: "POST",
      body: JSON.stringify({ action: "correct_manuscript" }),
    });
    if (res.workspace) _ebookWorkspaceState = res.workspace;
    const est = res.estimate || {};
    const ws = _ebookWorkspaceState || {};
    const idempotencyKey =
      "corr-" + String(projectId) + "-" + String(est.confirmation_token || "").slice(0, 12) + "-" + Date.now();
    confirmEl.innerHTML = `
      <h4 class="text-sm font-bold text-amber-900">Correction estimate (free)</h4>
      <p class="text-sm text-emerald-800">This estimate cost <b>$0.000</b>. No provider was called.</p>
      <p class="text-sm text-amber-900">${escapeHtml(est.label || "Request Correction")}</p>
      <p class="text-sm">Maximum remaining work if you confirm: <b>$${Number(est.max_total_usd != null ? est.max_total_usd : est.estimated_max_usd || 0).toFixed(3)}</b></p>
      <p class="text-sm">Per-chapter maximum: <b>$${Number(est.per_chapter_max_usd || 0.15).toFixed(3)}</b></p>
      <p class="text-sm">Accepted chapters: <b>${Number(est.accepted_chapter_count || 0)}</b> · Pending chapters: <b>${Number(est.pending_chapter_count || 0)}</b></p>
      <p class="text-xs text-amber-800">Spent $${Number(est.spent_usd || 0).toFixed(3)} · Remaining $${Number(est.remaining_usd || 0).toFixed(3)} · Cap $${Number(est.budget_cap_usd || 0).toFixed(2)}</p>
      <p class="text-xs text-slate-600">${escapeHtml(est.expires_note || "This estimate costs $0. Confirmation required before any paid call.")}</p>
      <label class="flex items-start gap-2 text-sm text-slate-800">
        <input type="checkbox" data-ws-authorize-paid class="mt-1">
        <span>I authorize a paid correction. Charge $0.15 per attempted chapter, up to the maximum above. Resume starts at the failed chapter only.</span>
      </label>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="btn-secondary text-sm" data-ws-cancel-confirm>Cancel</button>
        <button type="button" class="btn-primary text-sm" data-ws-confirm-correct disabled>Confirm and Correct Manuscript</button>
      </div>
    `;
    const authorizeBox = confirmEl.querySelector("[data-ws-authorize-paid]");
    const confirmBtn = confirmEl.querySelector("[data-ws-confirm-correct]");
    if (authorizeBox && confirmBtn) {
      authorizeBox.onchange = () => {
        confirmBtn.disabled = !authorizeBox.checked;
      };
    }
    confirmEl.querySelector("[data-ws-cancel-confirm]").onclick = async () => {
      try {
        await api(`/ebook-workspace/${projectId}/cancel-estimate`, { method: "POST", body: "{}" });
      } catch (e) { /* non-fatal */ }
      confirmEl.classList.add("hidden");
      confirmEl.innerHTML = "";
      toast("Cancelled — nothing spent.");
    };
    confirmEl.querySelector("[data-ws-confirm-correct]").onclick = async () => {
      const paidBox = confirmEl.querySelector("[data-ws-authorize-paid]");
      if (!paidBox || !paidBox.checked) {
        toast("Check the paid-authorization box before confirming. The estimate itself cost $0.", "error");
        return;
      }
      const btn = confirmEl.querySelector("[data-ws-confirm-correct]");
      setBusyEl(btn, true);
      confirmEl.querySelector("[data-ws-cancel-confirm]").disabled = true;
      try {
        const body = {
          confirmation_token: est.confirmation_token,
          expected_artifact_id: est.artifact_id || ws.artifact_id || "",
          expected_revision: est.artifact_revision != null ? est.artifact_revision : (ws.artifact_revision || 1),
          outline_digest: est.outline_digest || ws.outline_digest || "",
          max_authorized_usd: est.max_authorized_usd != null ? est.max_authorized_usd : est.estimated_max_usd,
          idempotency_key: idempotencyKey,
          authorize_paid_call: true,
        };
        const gen = await api(`/ebook-workspace/${projectId}/correct-manuscript`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        if (gen.workspace) {
          renderEbookWorkspace(gen.workspace);
        }
        confirmEl.classList.add("hidden");
        confirmEl.innerHTML = "";
        const st = (gen.result && gen.result.manuscript_status) || "";
        if (gen.duplicate) {
          toast("Already corrected for this confirmation — no extra charge.");
        } else if (st === "needs_correction") {
          toast("Correction still needs structural fixes.", "error");
        } else {
          toast("Correction complete — awaiting approval.");
        }
      } catch (e) {
        toast(e.message || String(e), "error");
        setBusyEl(btn, false);
        confirmEl.querySelector("[data-ws-cancel-confirm]").disabled = false;
      }
    };
  } catch (e) {
    confirmEl.innerHTML = `<p class="text-sm text-rose-700">${escapeHtml(e.message || String(e))}</p>`;
  }
}

async function estimateManuscriptInWorkspace(projectId) {
  const confirmEl = document.querySelector("[data-ws-confirm]");
  if (!confirmEl) return;
  confirmEl.classList.remove("hidden");
  confirmEl.innerHTML = `<p class="text-sm text-slate-700">Preparing cost estimate…</p>`;
  try {
    const res = await api(`/ebook-workspace/${projectId}/estimate-cost`, {
      method: "POST",
      body: JSON.stringify({ action: "generate_manuscript" }),
    });
    if (res.workspace) _ebookWorkspaceState = res.workspace;
    const est = res.estimate || {};
    const ws = _ebookWorkspaceState || {};
    const idempotencyKey =
      "ms-" + String(projectId) + "-" + String(est.confirmation_token || "").slice(0, 12) + "-" + Date.now();
    confirmEl.innerHTML = `
      <h4 class="text-sm font-bold text-amber-900">Confirm paid action</h4>
      <p class="text-sm text-amber-900">${escapeHtml(est.label || "Generate Manuscript")}</p>
      <p class="text-sm">Maximum total: <b>$${Number(est.max_total_usd != null ? est.max_total_usd : est.estimated_max_usd || 0).toFixed(3)}</b></p>
      <p class="text-sm">Per-chapter maximum: <b>$${Number(est.per_chapter_max_usd || 0.15).toFixed(3)}</b></p>
      <p class="text-sm">Accepted chapters: <b>${Number(est.accepted_chapter_count || 0)}</b> · Pending chapters: <b>${Number(est.pending_chapter_count || 0)}</b></p>
      <p class="text-xs text-amber-800">Spent $${Number(est.spent_usd || 0).toFixed(3)} · Remaining $${Number(est.remaining_usd || 0).toFixed(3)} · Cap $${Number(est.budget_cap_usd || 0).toFixed(2)}</p>
      <p class="text-xs text-slate-600">${escapeHtml(est.expires_note || "Confirmation required before any paid call. Opening this page does not spend.")}</p>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="btn-secondary text-sm" data-ws-cancel-confirm>Cancel</button>
        <button type="button" class="btn-primary text-sm" data-ws-confirm-generate>Confirm and Generate Manuscript</button>
      </div>
    `;
    confirmEl.querySelector("[data-ws-cancel-confirm]").onclick = async () => {
      try {
        await api(`/ebook-workspace/${projectId}/cancel-estimate`, { method: "POST", body: "{}" });
      } catch (e) { /* non-fatal */ }
      confirmEl.classList.add("hidden");
      confirmEl.innerHTML = "";
      toast("Cancelled — nothing spent.");
    };
    confirmEl.querySelector("[data-ws-confirm-generate]").onclick = async () => {
      const btn = confirmEl.querySelector("[data-ws-confirm-generate]");
      setBusyEl(btn, true);
      confirmEl.querySelector("[data-ws-cancel-confirm]").disabled = true;
      try {
        const body = {
          confirmation_token: est.confirmation_token,
          expected_artifact_id: est.artifact_id || ws.artifact_id || "",
          expected_revision: est.artifact_revision != null ? est.artifact_revision : (ws.artifact_revision || 1),
          outline_digest: est.outline_digest || ws.outline_digest || "",
          max_authorized_usd: est.max_authorized_usd != null ? est.max_authorized_usd : est.estimated_max_usd,
          idempotency_key: idempotencyKey,
        };
        const gen = await api(`/ebook-workspace/${projectId}/generate-manuscript`, {
          method: "POST",
          body: JSON.stringify(body),
        });
        if (gen.workspace) {
          renderEbookWorkspace(gen.workspace);
        }
        confirmEl.classList.add("hidden");
        confirmEl.innerHTML = "";
        const st = (gen.result && gen.result.manuscript_status) || "";
        if (gen.duplicate) {
          toast("Already generated for this confirmation — no extra charge.");
        } else if (st === "needs_correction") {
          toast("Manuscript generated but content QA needs correction.", "error");
        } else {
          toast("Manuscript generated — awaiting your approval.");
        }
      } catch (e) {
        toast(e.message || String(e), "error");
        setBusyEl(btn, false);
        confirmEl.querySelector("[data-ws-cancel-confirm]").disabled = false;
      }
    };
  } catch (e) {
    confirmEl.innerHTML = `<p class="text-sm text-rose-700">${escapeHtml(e.message || String(e))}</p>`;
  }
}

async function runEbook() {
  const source = document.getElementById("ebookInput").value.trim();
  if (!source) return toast("Enter a topic or URL", "error");
  const authorEl = document.getElementById("ebookAuthor");
  const researchEl = document.getElementById("ebookResearchNotes");
  const author = (authorEl && authorEl.value.trim()) || "";
  if (!author) return toast("Enter an author name for the finished ebook.", "error");
  const out = document.getElementById("ebookOutput");
  out.innerHTML = spinner("Fetching content and drafting your ebook...");
  setBusy("ebookBtn", true);
  try {
    const body = { source, author, author_brand: author };
    const researchNotes = (researchEl && researchEl.value.trim()) || "";
    if (researchNotes) body.research_notes = researchNotes;
    if (pendingEbookBrief) {
      body.contract = pendingEbookBrief;
      // Only attach project_id for legacy non-workspace plan builds.
      if (
        pendingEbookBrief._project_id != null &&
        !(pendingEbookBrief.ebook_project_workspace || pendingEbookBrief.ebook_workspace)
      ) {
        body.project_id = pendingEbookBrief._project_id;
      }
    }
    const data = await api("/generate-ebook", { method: "POST", body: JSON.stringify(body) });
    data.author_brand = author;
    data.product_type = "ebook";
    if (data.originality && data.originality.passed === false) {
      toast(
        `Originality ${(data.originality.score * 100).toFixed(1)}% is below 98%. Rewrite closer paraphrases before export.`,
        "error"
      );
    }
    renderEbook(data);
  } catch (e) {
    out.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusy("ebookBtn", false);
  }
}

// ---------- visual review (optional video resources) ----------
let ytMode = "link";

function initVisual() {
  setYtMode("link");
}

function setYtMode(mode) {
  ytMode = mode;
  document.getElementById("ytLinkPanel").classList.toggle("hidden", mode !== "link");
  document.getElementById("ytSearchPanel").classList.toggle("hidden", mode !== "search");
  document.querySelectorAll(".yt-tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.ytMode === mode);
  });
}

function ytRecoBadge(rec) {
  const map = {
    "Include as a resource": "bg-emerald-50 text-emerald-700",
    "Rewrite into original content": "bg-brand-50 text-brand-700",
    "Use as visual inspiration": "bg-amber-50 text-amber-700",
  };
  const cls = map[rec] || "bg-slate-100 text-slate-600";
  return `<span class="inline-flex rounded-full ${cls} text-xs font-medium px-3 py-1">${escapeHtml(rec) || "Suggestion"}</span>`;
}

async function saveYtResource(resource, createQr) {
  try {
    await api("/youtube/save-resource", {
      method: "POST",
      body: JSON.stringify({ resource, create_qr: !!createQr }),
    });
    toast(createQr ? "Saved with a QR code placeholder" : "Resource saved");
    loadProjects();
  } catch (e) {
    toast(e.message, "error");
  }
}

function ytResourceBar(getResource) {
  const bar = document.createElement("div");
  bar.className = "mt-4 flex flex-wrap justify-end gap-2";
  const saveBtn = document.createElement("button");
  saveBtn.className = "rounded-xl border border-brand-500 text-brand-700 hover:bg-brand-50 px-4 py-2 text-sm font-medium";
  saveBtn.textContent = "Save as Resource";
  saveBtn.onclick = () => saveYtResource(getResource(), false);
  const qrBtn = document.createElement("button");
  qrBtn.className = "btn-primary";
  qrBtn.textContent = "Create QR Code for Video Resource";
  qrBtn.onclick = () => saveYtResource(getResource(), true);
  bar.appendChild(saveBtn);
  bar.appendChild(qrBtn);
  return bar;
}

function ytAnalysisResource(d) {
  return {
    video_title: d.video_title || "",
    video_url: d.video_url || "",
    chapter_placement: d.suggested_placement || "",
    summary: d.summary || "",
    key_teaching_points: d.key_teaching_points || [],
    caption: d.caption || "",
    resource_note: d.resource_note || "",
  };
}

function renderYtAnalysis(d) {
  const out = document.getElementById("ytOutput");
  const transcriptBadge = d.transcript_available
    ? '<span class="inline-flex rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium px-3 py-1">Transcript used as research</span>'
    : '<span class="inline-flex rounded-full bg-amber-50 text-amber-700 text-xs font-medium px-3 py-1">No transcript available</span>';
  out.innerHTML = card(`
    <div class="flex flex-wrap items-start justify-between gap-3 mb-4">
      <div class="min-w-0">
        <div class="text-xs font-medium text-slate-500">Video analysis</div>
        <div class="text-lg font-bold text-slate-900">${escapeHtml(d.video_title) || "YouTube video"}</div>
        <a href="${escapeHtml(safeUrl(d.video_url))}" target="_blank" rel="noopener" class="text-xs text-brand-600 hover:text-brand-800 break-all">${escapeHtml(d.video_url)}</a>
      </div>
      <div class="flex flex-wrap items-center gap-2">${transcriptBadge}${ytRecoBadge(d.recommendation)}</div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
      <div class="md:col-span-2">${block("Summary", `<p class="text-sm text-slate-700">${escapeHtml(d.summary)}</p>`)}</div>
      <div class="md:col-span-2">${block("Key teaching points", bullets(d.key_teaching_points))}</div>
      ${block("Suggested chapter / section", `<p class="text-sm text-slate-700">${escapeHtml(d.suggested_placement)}</p>`)}
      ${block("How to use it", `<p class="text-sm text-slate-700">${escapeHtml(d.recommendation_reason)}</p>`)}
      ${block("Suggested caption", `<p class="text-sm text-slate-700">${escapeHtml(d.caption)}</p>`)}
      ${block("Resource note", `<p class="text-sm text-slate-700">${escapeHtml(d.resource_note)}</p>`)}
    </div>
  `);
  out.querySelector(".rounded-2xl").appendChild(ytResourceBar(() => ytAnalysisResource(d)));
}

function renderYtSearch(d) {
  const out = document.getElementById("ytOutput");
  if (d.mode === "suggestions") {
    out.innerHTML = card(`
      <div class="mb-3 flex items-center gap-2">
        <span class="inline-flex rounded-full bg-amber-50 text-amber-700 text-xs font-medium px-3 py-1">Search phrases only</span>
      </div>
      <p class="text-sm text-slate-600 mb-3">${escapeHtml(d.note)}</p>
      <h4 class="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-2">Suggested YouTube searches</h4>
      ${chips(d.search_phrases)}
    `);
    return;
  }
  const videos = d.videos || [];
  if (!videos.length) {
    out.innerHTML = card('<p class="text-sm text-slate-500">No videos were found. Try a different topic.</p>');
    return;
  }
  out.innerHTML = `<div class="space-y-4">
    <div class="flex items-center justify-between gap-3">
      <h3 class="text-base font-bold text-slate-900">Recommended videos</h3>
      <span class="inline-flex rounded-full bg-emerald-50 text-emerald-700 text-xs font-medium px-3 py-1">Live results</span>
    </div>
    <div class="space-y-4" id="ytVideoList"></div>
  </div>`;
  const list = document.getElementById("ytVideoList");
  videos.forEach((v) => {
    const el = document.createElement("div");
    el.className = "rounded-2xl border border-slate-200 bg-white p-5";
    el.innerHTML = `
      <div class="font-bold text-slate-900 mb-1">${escapeHtml(v.video_title)}</div>
      <a href="${escapeHtml(safeUrl(v.video_url))}" target="_blank" rel="noopener" class="text-xs text-brand-600 hover:text-brand-800 break-all">${escapeHtml(v.video_url)}</a>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
        ${block("Why it's useful", `<p class="text-sm text-slate-700">${escapeHtml(v.why_useful)}</p>`)}
        ${block("Suggested placement", `<p class="text-sm text-slate-700">${escapeHtml(v.suggested_placement)}</p>`)}
        ${block("Suggested caption", `<p class="text-sm text-slate-700">${escapeHtml(v.caption)}</p>`)}
        ${block("Resource note", `<p class="text-sm text-slate-700">${escapeHtml(v.resource_note)}</p>`)}
      </div>`;
    const resource = {
      video_title: v.video_title || "",
      video_url: v.video_url || "",
      chapter_placement: v.suggested_placement || "",
      summary: v.why_useful || "",
      key_teaching_points: [],
      caption: v.caption || "",
      resource_note: v.resource_note || "",
    };
    el.appendChild(ytResourceBar(() => resource));
    list.appendChild(el);
  });
}

function renderSavedYtResource(d) {
  const out = document.getElementById("ytOutput");
  const qr = d.qr_code
    ? `<div class="mt-4 rounded-xl border border-dashed border-brand-300 bg-brand-50/40 p-4">
        <div class="text-xs font-semibold uppercase tracking-wide text-brand-700 mb-1">QR code (placeholder)</div>
        <p class="text-sm text-slate-700">Encodes: <span class="break-all">${escapeHtml(d.qr_code.encodes)}</span></p>
        <p class="text-xs text-slate-500 mt-1">${escapeHtml(d.qr_code.note)}</p>
      </div>`
    : "";
  out.innerHTML = card(`
    <div class="mb-3">
      <div class="text-xs font-medium text-slate-500">Saved video resource</div>
      <div class="text-lg font-bold text-slate-900">${escapeHtml(d.video_title) || "YouTube resource"}</div>
      <a href="${escapeHtml(d.video_url)}" target="_blank" rel="noopener" class="text-xs text-brand-600 hover:text-brand-800 break-all">${escapeHtml(d.video_url)}</a>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
      ${block("Chapter placement", `<p class="text-sm text-slate-700">${escapeHtml(d.chapter_placement)}</p>`)}
      ${block("Summary", `<p class="text-sm text-slate-700">${escapeHtml(d.summary)}</p>`)}
      <div class="md:col-span-2">${block("Key teaching points", bullets(d.key_teaching_points))}</div>
      ${block("Caption", `<p class="text-sm text-slate-700">${escapeHtml(d.caption)}</p>`)}
      ${block("Resource note", `<p class="text-sm text-slate-700">${escapeHtml(d.resource_note)}</p>`)}
    </div>
    ${qr}
  `);
}

async function runYtAnalyze() {
  const url = document.getElementById("ytUrl").value.trim();
  if (!url) return toast("Paste a YouTube link", "error");
  const chapter_topic = document.getElementById("ytLinkTopic").value.trim();
  const out = document.getElementById("ytOutput");
  out.innerHTML = spinner("Analyzing the video...");
  setBusy("ytAnalyzeBtn", true);
  try {
    const data = await api("/youtube/analyze", { method: "POST", body: JSON.stringify({ url, chapter_topic }) });
    renderYtAnalysis(data);
  } catch (e) {
    out.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusy("ytAnalyzeBtn", false);
  }
}

async function runYtSearch() {
  const topic = document.getElementById("ytTopic").value.trim();
  if (!topic) return toast("Enter a topic to search", "error");
  const out = document.getElementById("ytOutput");
  out.innerHTML = spinner("Searching for helpful videos...");
  setBusy("ytSearchBtn", true);
  try {
    const data = await api("/youtube/search", { method: "POST", body: JSON.stringify({ topic }) });
    renderYtSearch(data);
  } catch (e) {
    out.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusy("ytSearchBtn", false);
  }
}

// ---------- publishing studio ----------
const PUB_SOURCE_TYPES = ["ebook", "product", "product_plan"];
const PUB_DEFAULT_DISCLAIMER =
  "The information in this book is provided for general educational purposes only. While every effort has been made to ensure accuracy, the author and publisher make no guarantees and accept no liability for any outcomes resulting from the use of this material.";

const pubState = {
  template: null,
  generated: null,
  projects: [],
  pendingSourceId: null,
  pendingPrefill: false,
};

function initPublishing() {
  loadPubTemplates();
  loadPubSources();
  loadPubAids();
}

function pubDerive(project) {
  const d = project.data || {};
  if (project.type === "product") return { title: d.title || project.name || "", subtitle: "" };
  if (project.type === "ebook") return { title: project.name || "", subtitle: "" };
  if (project.type === "product_plan") {
    const plan = d.plan || {};
    return { title: plan.product_title || project.name || "", subtitle: plan.subtitle || "" };
  }
  return { title: project.name || "", subtitle: "" };
}

function prefillPubDetails(project) {
  const form = document.getElementById("pubForm");
  if (!form) return;
  const { title, subtitle } = pubDerive(project);
  const year = new Date().getFullYear();
  form.elements.product_title.value = title;
  form.elements.subtitle.value = subtitle;
  if (!form.elements.copyright_text.value) form.elements.copyright_text.value = `Copyright ${year}. All rights reserved.`;
  if (!form.elements.disclaimer.value) form.elements.disclaimer.value = PUB_DEFAULT_DISCLAIMER;
}

async function loadPubSources() {
  const sel = document.getElementById("pubSource");
  if (!sel) return;
  let projects = [];
  try { projects = await api("/projects"); } catch (e) { /* ignore */ }
  pubState.projects = projects;
  const eligible = projects.filter((p) => PUB_SOURCE_TYPES.includes(p.type));
  sel.innerHTML =
    `<option value="">Select a saved project</option>` +
    eligible
      .map((p) => `<option value="${p.id}">${escapeHtml(p.name)} (${escapeHtml(typeLabelFor(p))})</option>`)
      .join("");
  if (pubState.pendingSourceId != null) {
    const proj = eligible.find((p) => String(p.id) === String(pubState.pendingSourceId));
    if (proj) {
      sel.value = String(pubState.pendingSourceId);
      if (pubState.pendingPrefill) prefillPubDetails(proj);
      pubState.pendingSourceId = null;
      pubState.pendingPrefill = false;
    }
  }
  sel.onchange = updatePubEditing;
  updatePubEditing();
}

// Show "Currently editing: <title>" + the project's workflow status above the
// publishing form so the user always knows which saved project they are working on.
function updatePubEditing() {
  const box = document.getElementById("pubEditing");
  const sel = document.getElementById("pubSource");
  if (!box || !sel) return;
  const proj = (pubState.projects || []).find((p) => String(p.id) === String(sel.value));
  if (!proj) {
    box.classList.add("hidden");
    box.innerHTML = "";
    return;
  }
  const stage = projectStage(proj);
  const statusBadge = stage
    ? `<span class="rounded-md ${STAGE_BADGE[stage]} text-xs font-semibold px-2 py-1">${escapeHtml(STAGE_LABELS[stage])}</span>`
    : "";
  box.classList.remove("hidden");
  box.innerHTML = `
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <span class="block text-xs font-medium text-slate-500">Currently editing</span>
        <span class="block truncate text-sm font-bold text-slate-900">${escapeHtml(proj.name)}</span>
      </div>
      ${statusBadge}
    </div>`;
}

function typeLabelFor(p) {
  if (p.type === "product") return (p.data && p.data.product_label) || "Product";
  if (p.type === "ebook") return "Ebook";
  if (p.type === "product_plan") return "Product Plan";
  return p.type;
}

async function loadPubAids() {
  const wrap = document.getElementById("pubAids");
  if (!wrap) return;
  let projects = pubState.projects;
  if (!projects.length) {
    try { projects = await api("/projects"); pubState.projects = projects; } catch (e) { /* ignore */ }
  }
  const aids = projects.filter((p) => p.type === "youtube_resource");
  if (!aids.length) {
    wrap.innerHTML = `<p class="text-sm text-slate-400">No saved video resources yet. Add some in Visual Review.</p>`;
    return;
  }
  wrap.innerHTML = aids
    .map(
      (p) => `<label class="flex items-start gap-3 rounded-xl border border-slate-100 hover:border-brand-200 px-3 py-2 cursor-pointer">
        <input type="checkbox" data-aid-id="${p.id}" class="mt-1 accent-brand-600" />
        <span class="min-w-0">
          <span class="block text-sm font-medium text-slate-800 truncate">${escapeHtml((p.data && p.data.video_title) || p.name)}</span>
          <span class="block text-xs text-slate-400 truncate">${escapeHtml((p.data && p.data.video_url) || "")}</span>
        </span>
      </label>`
    )
    .join("");
}

function loadPubTemplates() {
  const wrap = document.getElementById("pubTemplates");
  if (!wrap) return;
  if (pubState.templates) return renderPubTemplates();
  api("/publishing/templates")
    .then((list) => {
      pubState.templates = list;
      if (!pubState.template && list.length) pubState.template = list[0].id;
      renderPubTemplates();
    })
    .catch(() => {
      wrap.innerHTML = `<p class="text-sm text-rose-600">Could not load templates.</p>`;
    });
}

function renderPubTemplates() {
  const wrap = document.getElementById("pubTemplates");
  if (!wrap || !pubState.templates) return;
  wrap.innerHTML = "";
  pubState.templates.forEach((t) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className =
      "flex flex-col items-start gap-1 rounded-xl border px-4 py-3 text-left transition " +
      (pubState.template === t.id
        ? "border-brand-500 bg-brand-50 ring-2 ring-brand-200"
        : "border-slate-200 hover:border-brand-300 hover:bg-brand-50/40");
    btn.innerHTML = `<span class="text-sm font-semibold text-slate-800">${escapeHtml(t.name)}</span>
      <span class="text-xs text-slate-500">${escapeHtml(t.desc)}</span>`;
    btn.onclick = () => { pubState.template = t.id; renderPubTemplates(); };
    wrap.appendChild(btn);
  });
}

function collectPubDetails() {
  const form = document.getElementById("pubForm");
  const details = {};
  new FormData(form).forEach((v, k) => { details[k] = v; });
  return details;
}

function collectPubAidIds() {
  return Array.from(document.querySelectorAll("#pubAids input[data-aid-id]:checked")).map(
    (el) => Number(el.dataset.aidId)
  );
}

async function runPublishingPreview() {
  const projectId = document.getElementById("pubSource").value;
  if (!projectId) return toast("Select a project to publish", "error");
  if (!pubState.template) return toast("Choose a template", "error");

  const out = document.getElementById("pubOutput");
  out.innerHTML = spinner("Formatting your ebook preview...");
  setBusy("pubGenerateBtn", true);
  try {
    const data = await api("/generate-publishing", {
      method: "POST",
      body: JSON.stringify({
        project_id: Number(projectId),
        template: pubState.template,
        details: collectPubDetails(),
        visual_aid_ids: collectPubAidIds(),
      }),
    });
    renderPubPreview(data);
  } catch (e) {
    out.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusy("pubGenerateBtn", false);
  }
}

function renderPubPreview(data) {
  pubState.generated = data;
  const tpl = (pubState.templates || []).find((t) => t.id === data.template);
  const out = document.getElementById("pubOutput");
  out.innerHTML = `
    <div class="rounded-2xl border border-slate-200 bg-white p-4">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-base font-bold text-slate-900">Ebook preview</h3>
        <span class="text-xs rounded-md bg-brand-100 text-brand-700 font-semibold px-2 py-1">${escapeHtml((tpl && tpl.name) || data.template)}</span>
      </div>
      <iframe id="pubFrame" title="Ebook preview" class="w-full rounded-xl border border-slate-200 bg-slate-100" style="height:80vh"
        sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"></iframe>
    </div>`;
  const frame = document.getElementById("pubFrame");
  frame.srcdoc = data.preview_html || "";
  const saveBtn = document.getElementById("pubSaveBtn");
  if (saveBtn) saveBtn.disabled = false;
  // Whenever a preview exists, surface the Next Steps / Final Output Options panel
  // OUTSIDE the iframe (below the preview) so the user always has visible buttons.
  markSourceStage(data.source_project_id, "publishing_preview_ready");
  showPubNextStep(data.source_project_id);
}

async function savePublishingLayout() {
  if (!pubState.generated) return toast("Generate a preview first", "error");
  const data = pubState.generated;
  const name = (data.details && data.details.product_title) || data.source_name || "Untitled Layout";
  try {
    await api("/save-publishing", { method: "POST", body: JSON.stringify({ name, data }) });
    await markSourceStage(data.source_project_id, "export_ready");
    toast("Publishing layout saved");
    updatePubEditing();
    await showPubNextStep(data.source_project_id);
    loadProjects();
  } catch (e) {
    toast(e.message, "error");
  }
}

// Always-visible "Next Steps / Final Output Options" panel, rendered OUTSIDE the
// preview iframe whenever a preview exists. Shows workflow buttons (Save Layout /
// Back to Factory / View Saved Project) plus Basic Downloads + on-demand Platform
// Packages, so the publishing workflow never dead-ends.
function pubWorkflowCard() {
  return card(
    `<h3 class="text-base font-bold text-slate-900 mb-1">Next Steps</h3>
     <p class="text-sm text-slate-500 mb-4">Save your publishing layout, or move on in the workflow.</p>
     <div class="flex flex-wrap gap-3">
       <button data-pub-save class="btn-primary">Save Publishing Layout</button>
       <button data-pub-factory class="${NS_BTN}">Back to Product Factory</button>
       <button data-pub-saved class="${NS_BTN}">View Saved Project</button>
     </div>`
  );
}

function wirePubWorkflowIn(container) {
  if (!container) return;
  const save = container.querySelector("[data-pub-save]");
  if (save) save.onclick = () => savePublishingLayout();
  const factory = container.querySelector("[data-pub-factory]");
  if (factory) factory.onclick = () => go("factory");
  const saved = container.querySelector("[data-pub-saved]");
  if (saved) saved.onclick = () => go("saved");
}

async function showPubNextStep(sourceId) {
  const out = document.getElementById("pubOutput");
  if (!out) return;
  let panel = document.getElementById("pubNextStep");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "pubNextStep";
    panel.className = "mt-6 space-y-4";
    out.appendChild(panel);
  }
  if (sourceId == null) {
    // No linked source product: still show the workflow buttons so the user is
    // never stuck (downloads need a source product, so explain that).
    panel.innerHTML =
      pubWorkflowCard() +
      card(`<p class="text-sm text-slate-500">Save this layout to generate downloads and marketplace packages.</p>`);
    wirePubWorkflowIn(panel);
    return;
  }
  panel.innerHTML = pubWorkflowCard() + spinner("Preparing your final output options...");
  wirePubWorkflowIn(panel);
  try {
    // Reuse a persisted export when one already exists; only build a new one when
    // missing, so repeated previews/reopens never pile up duplicate export packages.
    let src = null;
    try { src = await api(`/projects/${sourceId}`); } catch (e) { /* non-fatal */ }
    let exports = (src && src.data && (src.data.product_exports || src.data.exports)) || null;
    if (!exports || !exports.files) {
      const r = await api("/export-product", {
        method: "POST",
        body: JSON.stringify({ project_id: sourceId }),
      });
      exports = r.exports;
    }
    const existingPackages = (src && src.data && src.data.packages) || {};
    const productType = (src && src.data && src.data.product_type) || "";
    panel.innerHTML = pubWorkflowCard() + finalOutputCard(sourceId, exports, existingPackages, productType);
    wirePubWorkflowIn(panel);
    wireFinalOutputIn(panel, sourceId, exports);
  } catch (e) {
    panel.innerHTML =
      pubWorkflowCard() +
      card(`<p class="text-sm text-rose-600">${escapeHtml(e.message)}</p>`);
    wirePubWorkflowIn(panel);
  }
}

// Advance the source product forward along the pipeline (preview -> export_ready ->
// completed) so its Dashboard Next Step stays correct (the publishing layout stays a
// separate saved artifact).
async function markSourceStage(sourceId, targetStage) {
  if (sourceId == null) return;
  try {
    const src = await api(`/projects/${sourceId}`);
    if (!src || (src.type !== "product" && src.type !== "ebook")) return;
    const sdata = src.data || {};
    // Only advance forward along the pipeline; never downgrade a project.
    const cur = STAGE_ORDER.indexOf(sdata.stage);
    const next = STAGE_ORDER.indexOf(targetStage);
    if (next < 0 || next <= cur) return;
    sdata.stage = targetStage;
    await api(`/projects/${sourceId}`, {
      method: "PUT",
      body: JSON.stringify({ name: src.name, type: src.type, data: sdata }),
    });
  } catch (e) {
    /* non-fatal: the layout is already saved */
  }
}

function renderSavedPublishing(d) {
  pubState.template = d.template || null;
  pubState.pendingSourceId = d.source_project_id != null ? d.source_project_id : null;
  renderPubTemplates();
  const form = document.getElementById("pubForm");
  if (form) {
    Object.entries(d.details || {}).forEach(([k, v]) => {
      const el = form.elements[k];
      if (el) el.value = v;
    });
  }
  const sel = document.getElementById("pubSource");
  if (sel && pubState.pendingSourceId != null && sel.querySelector(`option[value="${pubState.pendingSourceId}"]`)) {
    sel.value = String(pubState.pendingSourceId);
    pubState.pendingSourceId = null;
  }
  renderPubPreview(d);
}

// ---------- ad ----------
// Selected platforms for traffic content generation
let selectedPlatforms = [];

// Prefill state for traffic content form
let adPrefillContext = null;

function renderAd(d) {
  // Legacy: render a plain 30-second ad script (from reopened ad projects)
  const out = document.getElementById("adOutput");
  if (d.script) {
    out.innerHTML = card(`<h3 class="text-base font-bold text-slate-900 mb-3">30-Second Ad Script</h3><div class="prose-out">${md(d.script)}</div>`);
    out.appendChild(saveBar("ad", () => d));
    return;
  }
  // New traffic content: re-render the form with prefill from saved context
  if (d.funnel_context || d.ad_content) {
    prefillAdForm(d.funnel_context || d.ad_content);
  }
}

// Platform button selection
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".platform-btn");
  if (!btn) return;
  const p = btn.dataset.platform;
  if (!p) return;
  btn.classList.toggle("border-brand-400");
  btn.classList.toggle("text-brand-600");
  btn.classList.toggle("bg-brand-50");
  btn.classList.toggle("border-slate-300");
  btn.classList.toggle("text-slate-600");
  if (selectedPlatforms.includes(p)) {
    selectedPlatforms = selectedPlatforms.filter((x) => x !== p);
  } else {
    selectedPlatforms.push(p);
  }
});

// adPrefillContext is declared at the top of the ad/traffic section

function prefillAdForm(ctx) {
  if (!ctx) return;
  adPrefillContext = ctx;
  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el && val) el.value = val;
  };
  set("adProductTitle", ctx.product_title);
  set("adAudience", ctx.target_audience);
  set("adProblem", ctx.customer_problem);
  set("adPromise", ctx.product_promise);
  set("adProductDesc", ctx.product_description);
  set("adPrice", ctx.price);
  set("adFreebie", ctx.freebie_name);
  set("adLandingUrl", ctx.landing_page_url);
  set("adPaidUrl", ctx.paid_product_url);
  // Promotion goal radio
  const goalRadios = document.querySelectorAll('input[name="adPromoGoal"]');
  for (const r of goalRadios) { r.checked = (r.value === (ctx.promotion_goal || "freebie_signups")); }
  // Show context badge
  const badge = document.getElementById("adContextBadge");
  if (badge && ctx.product_title) {
    badge.textContent = "From: " + ctx.product_title;
    badge.classList.remove("hidden");
  }
}

function _adFormContext() {
  const goalRadio = document.querySelector('input[name="adPromoGoal"]:checked');
  return {
    product_title: document.getElementById("adProductTitle")?.value.trim() || "",
    product_type: "digital product",
    target_audience: document.getElementById("adAudience")?.value.trim() || "",
    customer_problem: document.getElementById("adProblem")?.value.trim() || "",
    product_promise: document.getElementById("adPromise")?.value.trim() || "",
    product_description: document.getElementById("adProductDesc")?.value.trim() || "",
    price: document.getElementById("adPrice")?.value.trim() || "",
    freebie_name: document.getElementById("adFreebie")?.value.trim() || "",
    landing_page_url: document.getElementById("adLandingUrl")?.value.trim() || "",
    paid_product_url: document.getElementById("adPaidUrl")?.value.trim() || "",
    tone: document.getElementById("adTone")?.value || "empathetic and understanding",
  };
}

async function runPromotionPackage() {
  const title = document.getElementById("adProductTitle")?.value.trim();
  if (!title) return toast("Enter a product title", "error");
  const out = document.getElementById("adOutput");
  const goalRadio = document.querySelector('input[name="adPromoGoal"]:checked');
  const goal = goalRadio?.value || "freebie_signups";
  const includePaid = document.getElementById("adIncludePaid")?.checked || false;
  out.innerHTML = spinner(`Generating full promotion package...`);
  setBusy("adBtn", true);
  try {
    const funnel_context = _adFormContext();
    const data = await api("/generate-promotion-package", {
      method: "POST",
      body: JSON.stringify({
        funnel_context,
        promotion_goal: goal,
        include_paid_ads: includePaid,
      }),
    });
    renderPromotionPackage(data, funnel_context);
  } catch (e) {
    out.innerHTML = card(`<p class="text-rose-600 text-sm">${escapeHtml(e.message)}</p>`);
  } finally {
    setBusy("adBtn", false);
  }
}

// Alias for backward compat
async function runTrafficContent() { await runPromotionPackage(); }
async function runAd() { await runPromotionPackage(); }

// ----- Promotion Package renderer -----
function renderPromotionPackage(data, funnel_context) {
  const out = document.getElementById("adOutput");
  adPrefillContext = funnel_context || _adFormContext();
  const pkg = data.package || {};
  const ctx = adPrefillContext;

  let html = `<div class="space-y-6">`;

  // Header
  html += `<div class="rounded-2xl border border-brand-200 bg-brand-50 p-4 flex flex-wrap items-center justify-between gap-3">
    <div>
      <div class="text-sm font-bold text-brand-800">Product Promotion Package</div>
      <div class="text-xs text-brand-600 mt-0.5">${escapeHtml(data.product_title || "")} &middot; ${escapeHtml(data.goal_label || "")}</div>
    </div>
    <div class="flex gap-2 flex-wrap">
      <button id="adSaveSetBtn" class="rounded-xl border border-brand-300 bg-white px-4 py-2 text-xs font-semibold text-brand-700 hover:bg-brand-100 transition">Save Package</button>
      <button id="adDownloadZipBtn" class="rounded-xl bg-brand-600 px-4 py-2 text-xs font-semibold text-white hover:bg-brand-700 transition">Download ZIP</button>
      <button id="adDownloadTxtBtn" class="rounded-xl border border-brand-300 bg-white px-4 py-2 text-xs font-semibold text-brand-700 hover:bg-brand-100 transition">Download TXT</button>
    </div>
  </div>`;

  // Section 1: Short Video Scripts
  if (pkg.short_video_scripts?.length) {
    html += _renderSection("Short Video Scripts", "Scripts for TikTok, Instagram Reels & YouTube Shorts", pkg.short_video_scripts, (s) => {
      const hook = s.hook ? `**HOOK (first 3s):** ${s.hook}` : "";
      const prob = s.problem_statement ? `\n**Problem:** ${s.problem_statement}` : "";
      const val = s.quick_value ? `\n**Quick Value:** ${s.quick_value}` : "";
      const script = s.spoken_script ? `\n**Script:**\n${s.spoken_script}` : "";
      const onScreen = s.on_screen_text ? `\n**On-Screen Text:** ${s.on_screen_text}` : "";
      const vis = s.visual_direction ? `\n**Visual:** ${s.visual_direction}` : "";
      const cta = s.cta ? `\n**CTA:** ${s.cta}` : "";
      const len = s.length ? `\n**Length:** ${s.length}` : "";
      const plat = s.platform ? `\n**Platform:** ${s.platform}` : "";
      return hook + prob + val + script + onScreen + vis + cta + len + plat;
    });
  }

  // Section 2: YouTube Thumbnails
  if (pkg.youtube_thumbnails?.length) {
    html += _renderSection("YouTube Thumbnail Ideas", "5 thumbnail concepts for YouTube", pkg.youtube_thumbnails, (t) => {
      const title = t.title_text ? `**Thumbnail Text:** ${t.title_text}` : "";
      const vis = t.visual_concept ? `\n**Visual:** ${t.visual_concept}` : "";
      const emo = t.emotional_angle ? `\n**Emotion:** ${t.emotional_angle}` : "";
      const color = t.color_direction ? `\n**Color/Style:** ${t.color_direction}` : "";
      const design = t.design_notes ? `\n**Design:** ${t.design_notes}` : "";
      return title + vis + emo + color + design;
    });
  }

  // Section 3: YouTube Video Titles
  if (pkg.youtube_titles) {
    const yt = pkg.youtube_titles;
    html += `<div class="rounded-2xl border border-slate-200 bg-white overflow-hidden">
      <div class="px-5 py-4 border-b border-slate-100 bg-slate-50">
        <h3 class="text-sm font-bold text-slate-800">YouTube Video Titles</h3>
        <p class="text-xs text-slate-500 mt-0.5">10 searchable, 5 curiosity, 5 how-to titles</p>
      </div>
      <div class="divide-y divide-slate-100">`;
    if (yt.searchable?.length) html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">Searchable</p>${yt.searchable.map(t => _contentItem(t, t.slice(0,60))).join("")}</div>`;
    if (yt.curiosity?.length) html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">Curiosity</p>${yt.curiosity.map(t => _contentItem(t, t.slice(0,60))).join("")}</div>`;
    if (yt.howto?.length) html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">How-To</p>${yt.howto.map(t => _contentItem(t, t.slice(0,60))).join("")}</div>`;
    html += `</div></div>`;
  }

  // Section 4: Pinterest Package — handle both dict and list formats
  if (pkg.pinterest_pins) {
    const pp = pkg.pinterest_pins;
    const isList = Array.isArray(pp);
    html += `<div class="rounded-2xl border border-slate-200 bg-white overflow-hidden">
      <div class="px-5 py-4 border-b border-slate-100 bg-slate-50">
        <h3 class="text-sm font-bold text-slate-800">Pinterest Package</h3>
        <p class="text-xs text-slate-500 mt-0.5">${isList ? pp.length + " pins" : (pp.titles?.length || 0) + " titles, " + (pp.descriptions?.length || 0) + " descriptions"}</p>
      </div>
      <div class="divide-y divide-slate-100">`;
    if (isList) {
      html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">Pins</p>${pp.map((p, i) => {
        const title = p.title || p.pin_title || `Pin ${i+1}`;
        const desc = p.description || p.desc || "";
        return _contentItem(title, (title + " " + desc).slice(0, 80));
      }).join("")}</div>`;
    } else {
      if (pp.titles?.length) html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">Pin Titles</p>${pp.titles.map(t => _contentItem(t, t.slice(0,60))).join("")}</div>`;
      if (pp.descriptions?.length) html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">Pin Descriptions</p>${pp.descriptions.map(d => _contentItem(d, d.slice(0,80))).join("")}</div>`;
      if (pp.design_ideas?.length) html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">Design Ideas</p>${pp.design_ideas.map(d => _contentItem(d, d.slice(0,80))).join("")}</div>`;
      if (pp.keywords?.length) html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">Keywords / Hashtags</p><div class="text-sm text-slate-700">${pp.keywords.join(", ")}</div></div>`;
    }
    html += `</div></div>`;
  }

  // Section 5: Facebook Posts
  if (pkg.facebook_posts?.length) {
    html += _renderSection("Facebook / Group Posts", "Value-first posts with soft CTAs", pkg.facebook_posts, (p) => {
      const post = typeof p === "string" ? p : (p.post_text || "");
      const cta = p.cta ? `\n\n**CTA:** ${p.cta}` : "";
      const angle = p.angle ? `\n**Angle:** ${p.angle}` : "";
      return post + cta + angle;
    });
  }

  // Section 6: Instagram Captions
  if (pkg.instagram_captions?.length) {
    html += _renderSection("Instagram Captions", "Captions with hooks, copy and hashtags", pkg.instagram_captions, (c) => {
      const hook = c.hook ? `**Hook:** ${c.hook}` : "";
      const cap = c.caption_text ? `\n${c.caption_text}` : "";
      const cta = c.cta ? `\n\n**CTA:** ${c.cta}` : "";
      const tags = c.hashtags ? `\n\n**Hashtags:** ${c.hashtags}` : "";
      return hook + cap + cta + tags;
    });
  }

  // Section 7: Threads / X Posts
  if (pkg.threads_posts?.length) {
    html += _renderSection("Threads / X Posts", "15 short posts — tips, curiosity, questions, stories", pkg.threads_posts, (p) => {
      const post = typeof p === "string" ? p : (p.post_text || "");
      const type = p.type ? `\n**Type:** ${p.type}` : "";
      const cta = p.cta_variation ? `\n**CTA:** ${p.cta_variation}` : "";
      return post + type + cta;
    });
  }

  // Section 8: Email Package
  if (pkg.email_package) {
    const ep = pkg.email_package;
    html += `<div class="rounded-2xl border border-slate-200 bg-white overflow-hidden">
      <div class="px-5 py-4 border-b border-slate-100 bg-slate-50">
        <h3 class="text-sm font-bold text-slate-800">Email Promotion Package</h3>
        <p class="text-xs text-slate-500 mt-0.5">Subject lines, short promos, launch email &amp; final reminder</p>
      </div>
      <div class="divide-y divide-slate-100">`;
    if (ep.subject_lines?.length) html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">Subject Lines (${ep.subject_lines.length})</p>${ep.subject_lines.map(s => _contentItem(s, s.slice(0,60))).join("")}</div>`;
    if (ep.short_promos?.length) {
      for (const promo of ep.short_promos) {
        const type = promo.email_type ? `**[${promo.email_type}]** ` : "";
        const subj = promo.subject ? `\n**Subject:** ${promo.subject}` : "";
        const body = promo.body ? `\n\n${promo.body}` : "";
        html += `<div class="px-5 py-3">${_contentItem(type + subj + body, (promo.subject || "Short promo").slice(0,60))}</div>`;
      }
    }
    if (ep.launch_email) {
      const le = ep.launch_email;
      const leText = (le.subject ? `**Subject:** ${le.subject}\n\n` : "") + (le.body || "");
      html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-emerald-700 bg-emerald-50 inline-block rounded px-2 py-0.5 mb-2">Launch Email</p>${_contentItem(leText, (le.subject || "Launch email").slice(0,60))}</div>`;
    }
    if (ep.final_reminder) {
      const fr = ep.final_reminder;
      const frText = (fr.subject ? `**Subject:** ${fr.subject}\n\n` : "") + (fr.body || "");
      html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-rose-700 bg-rose-50 inline-block rounded px-2 py-0.5 mb-2">Final Reminder</p>${_contentItem(frText, (fr.subject || "Final reminder").slice(0,60))}</div>`;
    }
    html += `</div></div>`;
  }

  // Section 9: Landing Page CTAs
  if (pkg.landing_page_ctas) {
    const lpc = pkg.landing_page_ctas;
    html += `<div class="rounded-2xl border border-slate-200 bg-white overflow-hidden">
      <div class="px-5 py-4 border-b border-slate-100 bg-slate-50">
        <h3 class="text-sm font-bold text-slate-800">Landing Page CTA Variations</h3>
        <p class="text-xs text-slate-500 mt-0.5">Button texts, headlines and subheadlines</p>
      </div>
      <div class="divide-y divide-slate-100">`;
    if (lpc.button_texts?.length) html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">Button Texts</p>${lpc.button_texts.map(t => _contentItem(t, t)).join("")}</div>`;
    if (lpc.headlines?.length) html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">Headline Options</p>${lpc.headlines.map(h => _contentItem(h, h.slice(0,60))).join("")}</div>`;
    if (lpc.subheadlines?.length) html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-2">Subheadline Options</p>${lpc.subheadlines.map(s => _contentItem(s, s.slice(0,60))).join("")}</div>`;
    html += `</div></div>`;
  }

  // Section 10: 7-Day Plan — handle both {days:[...]} and flat list
  if (pkg.seven_day_plan) {
    const plan = pkg.seven_day_plan;
    const days = Array.isArray(plan) ? plan : (plan.days || []);
    if (days.length) {
      html += `<div class="rounded-2xl border border-slate-200 bg-white overflow-hidden">
        <div class="px-5 py-4 border-b border-slate-100 bg-slate-50">
          <h3 class="text-sm font-bold text-slate-800">7-Day Free Traffic Plan</h3>
          <p class="text-xs text-slate-500 mt-0.5">Recommended daily posting schedule</p>
        </div>
        <div class="divide-y divide-slate-100">`;
      for (const day of days) {
        const angle = day.post_angle || day.angle || "";
        const cta = day.cta ? `\n**CTA:** ${day.cta}` : "";
        const note = day.posting_note || day.note ? `\n*${day.posting_note || day.note}*` : "";
        const line = `**Day ${day.day || day.day_number || "?"}** — ${day.platform || ""} (${day.content_type || ""})\n${angle}${cta}${note}`;
        html += `<div class="px-5 py-3">${_contentItem(line, `Day ${day.day || day.day_number || "?"}: ${angle.slice(0,60)}`)}</div>`;
      }
      html += `</div></div>`;
    }
  }

  // Section 11: Paid Ads
  if (pkg.paid_ads) {
    const pa = pkg.paid_ads;
    html += `<div class="rounded-2xl border border-slate-200 bg-white overflow-hidden">
      <div class="px-5 py-4 border-b border-slate-100 bg-amber-50">
        <h3 class="text-sm font-bold text-amber-800">Paid Ad Copy</h3>
        <p class="text-xs text-amber-600 mt-0.5">Facebook, short video and Google/YouTube ads</p>
      </div>
      <div class="divide-y divide-slate-100">`;
    if (pa.facebook_ads?.length) {
      for (const ad of pa.facebook_ads) {
        const text = [
          ad.headline ? `**Headline:** ${ad.headline}` : "",
          ad.primary_text ? `\n**Primary Text:**\n${ad.primary_text}` : "",
          ad.description ? `\n**Description:** ${ad.description}` : "",
          ad.cta ? `\n**CTA:** ${ad.cta}` : "",
        ].filter(Boolean).join("\n");
        html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-1">Facebook Ad</p>${_contentItem(text, ad.headline || "FB Ad")}</div>`;
      }
    }
    if (pa.short_video_ads?.length) {
      for (const ad of pa.short_video_ads) {
        const text = [
          ad.hook ? `**Hook:** ${ad.hook}` : "",
          ad.body ? `\n**Script:**\n${ad.body}` : "",
          ad.cta ? `\n**CTA:** ${ad.cta}` : "",
        ].filter(Boolean).join("\n");
        html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-1">Short Video Ad</p>${_contentItem(text, ad.hook || "Video Ad")}</div>`;
      }
    }
    if (pa.google_yt_ads?.length) {
      for (const ad of pa.google_yt_ads) {
        const text = [
          ad.headline1 ? `H1: ${ad.headline1}` : "",
          ad.headline2 ? `\nH2: ${ad.headline2}` : "",
          ad.headline3 ? `\nH3: ${ad.headline3}` : "",
          ad.description1 ? `\n\nDesc1: ${ad.description1}` : "",
          ad.description2 ? `\nDesc2: ${ad.description2}` : "",
        ].filter(Boolean).join("\n");
        html += `<div class="px-5 py-3"><p class="text-xs font-semibold text-slate-600 mb-1">Google/YouTube Ad</p>${_contentItem(text, ad.headline1 || "G Ads")}</div>`;
      }
    }
    html += `</div></div>`;
  }

  html += `</div>`;
  out.innerHTML = html;

  // Wire buttons
  const saveBtn = document.getElementById("adSaveSetBtn");
  if (saveBtn) saveBtn.onclick = () => _saveAdSet(data, ctx);
  const zipBtn = document.getElementById("adDownloadZipBtn");
  if (zipBtn) zipBtn.onclick = () => _downloadPromotionZip(data, ctx);
  const txtBtn = document.getElementById("adDownloadTxtBtn");
  if (txtBtn) txtBtn.onclick = () => _downloadPromotionTxt(data, ctx);
}

function _renderSection(title, subtitle, items, formatter) {
  if (!items?.length) return "";
  return `<div class="rounded-2xl border border-slate-200 bg-white overflow-hidden">
    <div class="px-5 py-4 border-b border-slate-100 bg-slate-50">
      <h3 class="text-sm font-bold text-slate-800">${title}</h3>
      <p class="text-xs text-slate-500 mt-0.5">${subtitle}</p>
    </div>
    <div class="divide-y divide-slate-100">
      ${items.map((item) => {
        const text = formatter(item);
        const label = typeof item === "string" ? item.slice(0, 60) : (item.hook || item.title_text || item.post_text || item.post || item.subject || item.caption_text || item.post_text || item.line || "Item");
        return `<div class="px-5 py-4">${_contentItem(text, label.slice(0, 80))}</div>`;
      }).join("")}
    </div>
  </div>`;
}

function _contentItem(text, label) {
  const id = "ct_" + Math.random().toString(36).slice(2, 10);
  return `<div class="flex items-start justify-between gap-3 mb-3 last:mb-0">
    <div class="text-sm text-slate-700 whitespace-pre-wrap flex-1">${md(text || "[content]")}</div>
    <button data-copy-id="${id}" class="shrink-0 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 hover:border-slate-300 transition">Copy</button>
  </div><textarea id="${id}" class="hidden">${(text || "").replace(/</g, "&lt;")}</textarea>`;
}

// Wire copy buttons (delegated)
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-copy-id]");
  if (!btn) return;
  const ta = document.getElementById(btn.dataset.copyId);
  if (!ta) return;
  navigator.clipboard.writeText(ta.value || "").then(() => {
    const orig = btn.textContent;
    btn.textContent = "Copied!";
    btn.classList.add("text-emerald-600", "border-emerald-300");
    setTimeout(() => { btn.textContent = orig; btn.classList.remove("text-emerald-600", "border-emerald-300"); }, 1500);
  }).catch(() => toast("Could not copy to clipboard", "error"));
});

async function _saveAdSet(data, funnel_context) {
  const name = prompt("Name this ad package:", data.product_title + " — Promotion Package") || data.product_title;
  if (!name) return;
  try {
    const r = await api("/save-ad-set", {
      method: "POST",
      body: JSON.stringify({ name, ad_content: data, funnel_context: funnel_context || _adFormContext() }),
    });
    toast("Package saved as: " + name + " (Project #" + r.id + ")");
  } catch (e) { toast("Could not save: " + e.message, "error"); }
}

function _downloadPromotionTxt(data, funnel_context) {
  const ctx = funnel_context || {};
  const lines = [];
  lines.push("PRODUCT PROMOTION PACKAGE");
  lines.push("=".repeat(50));
  lines.push(`Product: ${data.product_title}`);
  lines.push(`Goal: ${data.goal_label}`);
  lines.push(`Generated: ${new Date().toLocaleDateString()}`);
  lines.push("");

  const pkg = data.package || {};

  const _add = (label, items, fmt) => {
    if (!items?.length) return;
    lines.push(`\n${label}`);
    lines.push("-".repeat(40));
    items.forEach((item, i) => { lines.push(`\n--- ${i + 1} ---\n${fmt(item)}`); });
  };

  const _text = (t) => typeof t === "string" ? t : JSON.stringify(t, null, 2);

  // Video scripts
  if (pkg.short_video_scripts?.length) {
    lines.push("\nSHORT VIDEO SCRIPTS (TikTok / Instagram / YouTube)");
    lines.push("-".repeat(40));
    pkg.short_video_scripts.forEach((s, i) => {
      lines.push(`\n--- Script ${i + 1} [${s.platform || "video"}] ---`);
      if (s.hook) lines.push(`HOOK: ${s.hook}`);
      if (s.problem_statement) lines.push(`PROBLEM: ${s.problem_statement}`);
      if (s.quick_value) lines.push(`QUICK VALUE: ${s.quick_value}`);
      if (s.spoken_script) lines.push(`SCRIPT:\n${s.spoken_script}`);
      if (s.on_screen_text) lines.push(`ON-SCREEN TEXT: ${s.on_screen_text}`);
      if (s.visual_direction) lines.push(`VISUAL: ${s.visual_direction}`);
      if (s.cta) lines.push(`CTA: ${s.cta}`);
      if (s.length) lines.push(`LENGTH: ${s.length}`);
    });
  }

  // YouTube thumbnails
  if (pkg.youtube_thumbnails?.length) {
    lines.push("\nYOUTUBE THUMBNAIL IDEAS");
    lines.push("-".repeat(40));
    pkg.youtube_thumbnails.forEach((t, i) => {
      lines.push(`\n--- Thumbnail ${i + 1} ---`);
      if (t.title_text) lines.push(`TITLE TEXT: ${t.title_text}`);
      if (t.visual_concept) lines.push(`VISUAL: ${t.visual_concept}`);
      if (t.emotional_angle) lines.push(`EMOTION: ${t.emotional_angle}`);
      if (t.color_direction) lines.push(`COLOR/STYLE: ${t.color_direction}`);
      if (t.design_notes) lines.push(`DESIGN: ${t.design_notes}`);
    });
  }

  // YouTube titles
  if (pkg.youtube_titles) {
    const yt = pkg.youtube_titles;
    lines.push("\nYOUTUBE VIDEO TITLES");
    if (yt.searchable?.length) { lines.push("Searchable:"); yt.searchable.forEach(t => lines.push("  - " + t)); }
    if (yt.curiosity?.length) { lines.push("Curiosity:"); yt.curiosity.forEach(t => lines.push("  - " + t)); }
    if (yt.howto?.length) { lines.push("How-To:"); yt.howto.forEach(t => lines.push("  - " + t)); }
  }

  // Pinterest
  if (pkg.pinterest_pins) {
    const pp = pkg.pinterest_pins;
    lines.push("\nPINTEREST PACKAGE");
    if (pp.titles?.length) { lines.push("Titles:"); pp.titles.forEach(t => lines.push("  - " + t)); }
    if (pp.descriptions?.length) { lines.push("\nDescriptions:"); pp.descriptions.forEach(d => lines.push("  - " + d)); }
    if (pp.design_ideas?.length) { lines.push("\nDesign Ideas:"); pp.design_ideas.forEach(d => lines.push("  - " + d)); }
    if (pp.keywords?.length) { lines.push("\nKeywords:"); lines.push(pp.keywords.join(", ")); }
  }

  // Facebook
  if (pkg.facebook_posts?.length) {
    lines.push("\nFACEBOOK / GROUP POSTS");
    pkg.facebook_posts.forEach((p, i) => {
      lines.push(`\n--- Post ${i + 1} ---`);
      if (typeof p === "string") lines.push(p);
      else {
        if (p.post_text) lines.push(p.post_text);
        if (p.cta) lines.push(`\nCTA: ${p.cta}`);
        if (p.angle) lines.push(`Angle: ${p.angle}`);
      }
    });
  }

  // Instagram
  if (pkg.instagram_captions?.length) {
    lines.push("\nINSTAGRAM CAPTIONS");
    pkg.instagram_captions.forEach((c, i) => {
      lines.push(`\n--- Caption ${i + 1} ---`);
      if (c.hook) lines.push(`HOOK: ${c.hook}`);
      if (c.caption_text) lines.push(c.caption_text);
      if (c.cta) lines.push(`\nCTA: ${c.cta}`);
      if (c.hashtags) lines.push(`\nHASHTAGS: ${c.hashtags}`);
    });
  }

  // Threads
  if (pkg.threads_posts?.length) {
    lines.push("\nTHREADS / X POSTS");
    pkg.threads_posts.forEach((p, i) => {
      lines.push(`\n--- Post ${i + 1} [${p.type || "post"}] ---`);
      lines.push(p.post_text || p);
      if (p.cta_variation) lines.push(`CTA: ${p.cta_variation}`);
    });
  }

  // Email
  if (pkg.email_package) {
    const ep = pkg.email_package;
    lines.push("\nEMAIL PROMOTION PACKAGE");
    if (ep.subject_lines?.length) { lines.push("\nSubject Lines:"); ep.subject_lines.forEach(s => lines.push("  - " + s)); }
    if (ep.short_promos?.length) { lines.push("\nShort Promos:"); ep.short_promos.forEach((p, i) => {
      lines.push(`\n--- Promo ${i + 1} [${p.email_type || "nurture"}] ---`);
      if (p.subject) lines.push(`Subject: ${p.subject}`);
      if (p.body) lines.push(`Body:\n${p.body}`);
    }); }
    if (ep.launch_email) { lines.push("\nLAUNCH EMAIL:"); if (ep.launch_email.subject) lines.push(`Subject: ${ep.launch_email.subject}`); if (ep.launch_email.body) lines.push(`Body:\n${ep.launch_email.body}`); }
    if (ep.final_reminder) { lines.push("\nFINAL REMINDER:"); if (ep.final_reminder.subject) lines.push(`Subject: ${ep.final_reminder.subject}`); if (ep.final_reminder.body) lines.push(`Body:\n${ep.final_reminder.body}`); }
  }

  // Landing page CTAs
  if (pkg.landing_page_ctas) {
    const lpc = pkg.landing_page_ctas;
    lines.push("\nLANDING PAGE CTA VARIATIONS");
    if (lpc.button_texts?.length) { lines.push("Button Texts:"); lpc.button_texts.forEach(t => lines.push("  - " + t)); }
    if (lpc.headlines?.length) { lines.push("\nHeadlines:"); lpc.headlines.forEach(h => lines.push("  - " + h)); }
    if (lpc.subheadlines?.length) { lines.push("\nSubheadlines:"); lpc.subheadlines.forEach(s => lines.push("  - " + s)); }
  }

  // 7-day plan
  if (pkg.seven_day_plan?.days?.length) {
    lines.push("\n7-DAY FREE TRAFFIC PLAN");
    pkg.seven_day_plan.days.forEach((d) => {
      lines.push(`\nDay ${d.day} — ${d.platform} (${d.content_type})`);
      if (d.post_angle) lines.push(`  Angle: ${d.post_angle}`);
      if (d.cta) lines.push(`  CTA: ${d.cta}`);
      if (d.posting_note) lines.push(`  Note: ${d.posting_note}`);
    });
  }

  // Paid ads
  if (pkg.paid_ads) {
    const pa = pkg.paid_ads;
    lines.push("\nPAID AD COPY");
    if (pa.facebook_ads?.length) { lines.push("\nFacebook Ads:"); pa.facebook_ads.forEach((a) => {
      if (a.headline) lines.push(`  Headline: ${a.headline}`);
      if (a.primary_text) lines.push(`  Text:\n${a.primary_text}`);
      if (a.cta) lines.push(`  CTA: ${a.cta}`);
      lines.push("");
    }); }
    if (pa.short_video_ads?.length) { lines.push("\nShort Video Ads:"); pa.short_video_ads.forEach((a) => {
      if (a.hook) lines.push(`  Hook: ${a.hook}`);
      if (a.body) lines.push(`  Script:\n${a.body}`);
      if (a.cta) lines.push(`  CTA: ${a.cta}`);
      lines.push("");
    }); }
    if (pa.google_yt_ads?.length) { lines.push("\nGoogle/YouTube Ads:"); pa.google_yt_ads.forEach((a) => {
      if (a.headline1) lines.push(`  H1: ${a.headline1}`);
      if (a.headline2) lines.push(`  H2: ${a.headline2}`);
      if (a.headline3) lines.push(`  H3: ${a.headline3}`);
      if (a.description1) lines.push(`  Desc1: ${a.description1}`);
      if (a.description2) lines.push(`  Desc2: ${a.description2}`);
      lines.push("");
    }); }
  }

  // Links
  lines.push("\nLINKS");
  if (ctx.landing_page_url) lines.push(`  Landing Page: ${ctx.landing_page_url}`);
  if (ctx.freebie_name) lines.push(`  Free Giveaway: ${ctx.freebie_name}`);
  if (ctx.product_promise) lines.push(`  Product Promise: ${ctx.product_promise}`);

  const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = (data.product_title || "promotion-package").replace(/[^a-z0-9]/gi, "-") + "-promotion-package.txt";
  a.click();
  URL.revokeObjectURL(url);
  toast("TXT package downloaded!");
}

async function _downloadPromotionZip(data, funnel_context) {
  try {
    const ctx = funnel_context || {};
    const zip = new JSZip();
    const pkg = data.package || {};
    const safe = (s) => (s || "").replace(/[^a-z0-9_\-]/gi, "-").toLowerCase();

    // metadata.json
    zip.file("metadata.json", JSON.stringify({
      product_title: data.product_title,
      promotion_goal: data.promotion_goal,
      goal_label: data.goal_label,
      include_paid_ads: data.include_paid_ads,
      generated: new Date().toISOString(),
      funnel_context: ctx,
    }, null, 2));

    // Helper: add a file only if content is non-empty
    const add = (filename, content) => {
      if (content && content.trim()) zip.file(filename, content.trim());
    };

    // Short video scripts
    if (pkg.short_video_scripts?.length) {
      const scriptLines = pkg.short_video_scripts.map((s, i) => {
        return [`--- Script ${i + 1} [${s.platform || "video"}] ---`, `Length: ${s.length || "N/A"}`, "", `HOOK:`, s.hook || "", "", `PROBLEM:`, s.problem_statement || "", "", `QUICK VALUE:`, s.quick_value || "", "", `SPOKEN SCRIPT:`, s.spoken_script || "", "", `ON-SCREEN TEXT:`, s.on_screen_text || "", "", `VISUAL DIRECTION:`, s.visual_direction || "", "", `CTA:`, s.cta || ""].join("\n");
      }).join("\n\n" + "=".repeat(40) + "\n\n");
      add("tiktok_reels_scripts.txt", scriptLines);
    }

    // YouTube thumbnails + titles
    if (pkg.youtube_thumbnails?.length || pkg.youtube_titles) {
      let ytLines = [];
      if (pkg.youtube_thumbnails?.length) {
        ytLines.push("YOUTUBE THUMBNAIL IDEAS\n" + "=".repeat(40));
        pkg.youtube_thumbnails.forEach((t, i) => {
          ytLines.push(`\n--- Thumbnail ${i + 1} ---`);
          if (t.title_text) ytLines.push(`Title Text: ${t.title_text}`);
          if (t.visual_concept) ytLines.push(`Visual: ${t.visual_concept}`);
          if (t.emotional_angle) ytLines.push(`Emotion: ${t.emotional_angle}`);
          if (t.color_direction) ytLines.push(`Color/Style: ${t.color_direction}`);
          if (t.design_notes) ytLines.push(`Design Notes: ${t.design_notes}`);
        });
      }
      if (pkg.youtube_titles) {
        ytLines.push("\n\nYOUTUBE VIDEO TITLES\n" + "=".repeat(40));
        if (pkg.youtube_titles.searchable?.length) { ytLines.push("\nSearchable:"); pkg.youtube_titles.searchable.forEach(t => ytLines.push("  - " + t)); }
        if (pkg.youtube_titles.curiosity?.length) { ytLines.push("\nCuriosity:"); pkg.youtube_titles.curiosity.forEach(t => ytLines.push("  - " + t)); }
        if (pkg.youtube_titles.howto?.length) { ytLines.push("\nHow-To:"); pkg.youtube_titles.howto.forEach(t => ytLines.push("  - " + t)); }
      }
      add("youtube_titles_and_thumbnails.txt", ytLines.join("\n"));
    }

    // Pinterest — handle both dict {titles,descriptions,...} and flat list of pins
    if (pkg.pinterest_pins) {
      let pinLines = [];
      if (Array.isArray(pkg.pinterest_pins)) {
        // Flat list: each item has title/description/design_idea fields
        pkg.pinterest_pins.forEach((p, i) => {
          if (p.title || p.pin_title) pinLines.push(`${i + 1}. ${p.title || p.pin_title}`);
          if (p.description || p.desc) pinLines.push(`   ${p.description || p.desc}`);
          if (p.design_idea) pinLines.push(`   Design: ${p.design_idea}`);
        });
      } else {
        // Expected dict format
        if (pkg.pinterest_pins.titles?.length) { pinLines.push("PIN TITLES\n" + "-".repeat(40)); pkg.pinterest_pins.titles.forEach((t, i) => { pinLines.push(`${i + 1}. ${t}`); }); }
        if (pkg.pinterest_pins.descriptions?.length) { pinLines.push("\nDESCRIPTIONS\n" + "-".repeat(40)); pkg.pinterest_pins.descriptions.forEach((d, i) => { pinLines.push(`\n--- Pin ${i + 1} ---\n${d}`); }); }
        if (pkg.pinterest_pins.design_ideas?.length) { pinLines.push("\nDESIGN IDEAS\n" + "-".repeat(40)); pkg.pinterest_pins.design_ideas.forEach(d => { pinLines.push("  - " + d); }); }
        if (pkg.pinterest_pins.keywords?.length) { pinLines.push("\nKEYWORDS\n" + "-".repeat(40)); pinLines.push(pkg.pinterest_pins.keywords.join(", ")); }
      }
      if (pinLines.length) add("pinterest_pins.txt", pinLines.join("\n"));
    }

    // Facebook
    if (pkg.facebook_posts?.length) {
      const fbLines = pkg.facebook_posts.map((p, i) => {
        const text = typeof p === "string" ? p : (p.post_text || "");
        const cta = p.cta ? `\n\nCTA: ${p.cta}` : "";
        const angle = p.angle ? `\nAngle: ${p.angle}` : "";
        return `--- Post ${i + 1} ---${angle}\n${text}${cta}`;
      }).join("\n\n" + "=".repeat(40) + "\n\n");
      add("facebook_posts.txt", fbLines);
    }

    // Instagram
    if (pkg.instagram_captions?.length) {
      const igLines = pkg.instagram_captions.map((c, i) => {
        return [`--- Caption ${i + 1} ---`, c.hook ? `Hook: ${c.hook}` : "", c.caption_text || "", c.cta ? `\nCTA: ${c.cta}` : "", c.hashtags ? `\nHashtags: ${c.hashtags}` : ""].filter(Boolean).join("\n");
      }).join("\n\n" + "=".repeat(40) + "\n\n");
      add("instagram_captions.txt", igLines);
    }

    // Threads
    if (pkg.threads_posts?.length) {
      const thLines = pkg.threads_posts.map((p, i) => {
        return `--- Post ${i + 1} [${p.type || "post"}] ---\n${p.post_text || p}${p.cta_variation ? `\n\nCTA: ${p.cta_variation}` : ""}`;
      }).join("\n\n" + "=".repeat(40) + "\n\n");
      add("threads_posts.txt", thLines);
    }

    // Email
    if (pkg.email_package) {
      let emLines = [];
      const ep = pkg.email_package;
      if (ep.subject_lines?.length) { emLines.push("SUBJECT LINES\n" + "-".repeat(40)); ep.subject_lines.forEach(s => { emLines.push("  - " + s); }); }
      if (ep.short_promos?.length) {
        emLines.push("\nSHORT PROMO EMAILS\n" + "-".repeat(40));
        ep.short_promos.forEach((p, i) => {
          emLines.push(`\n--- Promo ${i + 1} [${p.email_type || "nurture"}] ---`);
          if (p.subject) emLines.push(`Subject: ${p.subject}`);
          if (p.body) emLines.push(`\nBody:\n${p.body}`);
        });
      }
      if (ep.launch_email) {
        emLines.push("\nLAUNCH EMAIL\n" + "-".repeat(40));
        if (ep.launch_email.subject) emLines.push(`Subject: ${ep.launch_email.subject}`);
        if (ep.launch_email.body) emLines.push(`\nBody:\n${ep.launch_email.body}`);
      }
      if (ep.final_reminder) {
        emLines.push("\nFINAL REMINDER EMAIL\n" + "-".repeat(40));
        if (ep.final_reminder.subject) emLines.push(`Subject: ${ep.final_reminder.subject}`);
        if (ep.final_reminder.body) emLines.push(`\nBody:\n${ep.final_reminder.body}`);
      }
      add("email_promos.txt", emLines.join("\n"));
    }

    // Landing page CTAs
    if (pkg.landing_page_ctas) {
      const lpcLines = [];
      if (pkg.landing_page_ctas.button_texts?.length) { lpcLines.push("BUTTON TEXTS\n" + "-".repeat(40)); pkg.landing_page_ctas.button_texts.forEach(t => { lpcLines.push("  " + t); }); }
      if (pkg.landing_page_ctas.headlines?.length) { lpcLines.push("\nHEADLINES\n" + "-".repeat(40)); pkg.landing_page_ctas.headlines.forEach(h => { lpcLines.push("  " + h); }); }
      if (pkg.landing_page_ctas.subheadlines?.length) { lpcLines.push("\nSUBHEADLINES\n" + "-".repeat(40)); pkg.landing_page_ctas.subheadlines.forEach(s => { lpcLines.push("  " + s); }); }
      add("landing_page_ctas.txt", lpcLines.join("\n"));
    }

    // 7-day plan — handle both {days:[...]} and flat list
    if (pkg.seven_day_plan) {
      const plan = pkg.seven_day_plan;
      const days = Array.isArray(plan) ? plan : (plan.days || []);
      if (days.length) {
        const planLines = days.map((d) => {
          return [`Day ${d.day || d.day_number || "?"} — ${d.platform || ""} (${d.content_type || ""})`, `  Angle: ${d.post_angle || d.angle || ""}`, d.cta ? `  CTA: ${d.cta}` : "", d.posting_note || d.note ? `  Note: ${d.posting_note || d.note}` : ""].filter(Boolean).join("\n");
        }).join("\n\n");
        add("posting_plan.txt", planLines);
      }
    }

    // Paid ads
    if (pkg.paid_ads) {
      let paidLines = [];
      if (pkg.paid_ads.facebook_ads?.length) {
        paidLines.push("FACEBOOK ADS\n" + "-".repeat(40));
        pkg.paid_ads.facebook_ads.forEach((a) => {
          if (a.headline) paidLines.push(`Headline: ${a.headline}`);
          if (a.primary_text) paidLines.push(`\nText:\n${a.primary_text}`);
          if (a.description) paidLines.push(`Description: ${a.description}`);
          if (a.cta) paidLines.push(`CTA: ${a.cta}`);
          paidLines.push("");
        });
      }
      if (pkg.paid_ads.short_video_ads?.length) {
        paidLines.push("\nSHORT VIDEO ADS\n" + "-".repeat(40));
        pkg.paid_ads.short_video_ads.forEach((a) => {
          if (a.hook) paidLines.push(`Hook: ${a.hook}`);
          if (a.body) paidLines.push(`\nScript:\n${a.body}`);
          if (a.cta) paidLines.push(`CTA: ${a.cta}`);
          paidLines.push("");
        });
      }
      if (pkg.paid_ads.google_yt_ads?.length) {
        paidLines.push("\nGOOGLE/YOUTUBE ADS\n" + "-".repeat(40));
        pkg.paid_ads.google_yt_ads.forEach((a) => {
          if (a.headline1) paidLines.push(`H1: ${a.headline1}`);
          if (a.headline2) paidLines.push(`H2: ${a.headline2}`);
          if (a.headline3) paidLines.push(`H3: ${a.headline3}`);
          if (a.description1) paidLines.push(`Desc1: ${a.description1}`);
          if (a.description2) paidLines.push(`Desc2: ${a.description2}`);
          paidLines.push("");
        });
      }
      add("paid_ads.txt", paidLines.join("\n"));
    }

    // ad_package.md (master summary)
    const mdLines = [`# ${data.product_title} — Promotion Package`, `Goal: ${data.goal_label}`, `Generated: ${new Date().toLocaleDateString()}`, ""];
    if (ctx.landing_page_url) mdLines.push(`Landing Page: ${ctx.landing_page_url}`);
    if (ctx.freebie_name) mdLines.push(`Free Giveaway: ${ctx.freebie_name}`);
    mdLines.push("", "See individual files for full content:");
    const fileOrder = ["tiktok_reels_scripts.txt","youtube_titles_and_thumbnails.txt","pinterest_pins.txt","facebook_posts.txt","instagram_captions.txt","threads_posts.txt","email_promos.txt","landing_page_ctas.txt","posting_plan.txt","paid_ads.txt"];
    fileOrder.forEach(f => mdLines.push(`- ${f}`));
    add("ad_package.md", mdLines.join("\n"));

    const blob = await zip.generateAsync({ type: "blob" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (data.product_title || "promotion-package").replace(/[^a-z0-9]/gi, "-") + "-promotion-package.zip";
    a.click();
    URL.revokeObjectURL(url);
    toast("ZIP package downloaded!");
  } catch (e) {
    toast("Could not create ZIP: " + e.message, "error");
  }
}

// Render the Launch Package panel: generate + display 8 sections + download ZIP
async function renderLaunchPackage(projectId, projectData) {
  const out = document.getElementById("adOutput") || document.createElement("div");
  if (!out.id) out.id = "adOutput";
  out.innerHTML = card(`<div class="flex items-center gap-3 py-2">
    <div class="animate-spin h-5 w-5 border-2 border-amber-600 border-t-transparent rounded-full"></div>
    <span class="text-sm text-slate-600">Generating your launch package — this takes about 60 seconds…</span>
  </div>`);
  out.classList.remove("hidden");
  go("ad");

  try {
    // Build funnel context from project data
    const funnelCtx = {
      product_title: projectData?.title || projectData?.name || "",
      audience: projectData?.target_audience || projectData?.audience || "",
      problem: projectData?.customer_problem || projectData?.problem || "",
      product_promise: projectData?.product_promise || projectData?.promise || "",
      product_description: projectData?.description || projectData?.product_description || "",
      price: projectData?.price || "",
      freebie_name: projectData?.freebie_name || projectData?.freebie || "",
      landing_page_url: projectData?.landing_page_url || "",
      paid_product_url: projectData?.paid_product_url || "",
      tone: projectData?.tone || "empathetic and understanding",
    };

    const r = await api("/generate-launch-package", {
      method: "POST",
      body: JSON.stringify({ project_id: projectId, funnel_context: funnelCtx }),
    });

    const pkg = r.package || r;
    _renderLaunchPackageUI(pkg, projectId, out);
  } catch (e) {
    out.innerHTML = card(`<p class="text-rose-600 text-sm">Launch package failed: ${escapeHtml(e.message)}</p>
      <button id="_lpRetryBtn" class="${NS_BTN} mt-3">Try Again</button>`);
    const retryBtn = document.getElementById("_lpRetryBtn");
    if (retryBtn) retryBtn.onclick = () => renderLaunchPackage(projectId, projectData);
  }
}

// Internal: render the generated launch package UI
function _renderLaunchPackageUI(pkg, projectId, out) {
  const lp = (label, icon) => `<div class="flex items-center gap-2 mb-2">
    <span class="text-amber-600 font-bold text-lg">${icon}</span>
    <h3 class="text-base font-bold text-slate-900">${label}</h3>
  </div>`;
  const section = (icon, title, content) => `
    <div class="rounded-xl border border-slate-200 bg-white p-5">
      ${lp(title, icon)}
      <div class="prose-out text-sm">${md(content)}</div>
    </div>`;

  // ── 1. Freebie Builder ───────────────────────────────────────────
  const fb = pkg.freebie || {};
  const freebieContent = `
**${fb.freebie_name || "[Name your freebie]"}**
*${fb.freebie_format || "Format: TBD"}*

${fb.freebie_description || ""}

**Page Count / Size:** ${fb.freebie_pages || "TBD"}

**Why This Freebie Works:**
${fb.why_this_freebie || ""}

**Opt-In Page Headline:** ${fb.freebie_optin_headline || ""}
**Opt-In Subheadline:** ${fb.freebie_optin_subheadline || ""}
`.trim();

  // ── 2. Opt-in Page ───────────────────────────────────────────────
  const op = pkg.optin_page || {};
  const optinItems = (op.what_you_get || []).map(i => `- ${i}`).join("\n");
  const optinFaq = (op.faq || []).map(f => `**Q: ${f.q || ""}**\n${f.a || ""}`).join("\n\n");
  const optinContent = `
**Headline:** ${op.headline || ""}

**Subheadline:** ${op.subheadline || ""}

**What They Get:**
${optinItems || "- [What they get]"}

**Sign-up CTA:** ${op.signup_cta || ""}

**Trust Section:**
${op.trust_section || ""}

${optinFaq ? `**FAQ:**\n${optinFaq}` : ""}
`.trim();

  // ── 3. Sales Page ───────────────────────────────────────────────
  const sp = pkg.sales_page || {};
  const spIncluded = (sp.whats_included || []).map(i => `- ${i}`).join("\n");
  const spFaq = (sp.faq || []).map(f => `**Q: ${f.q || ""}**\n${f.a || ""}`).join("\n\n");
  const salesContent = `
**Headline:** ${sp.headline || ""}

**Problem:**
${sp.problem_section || ""}

**Promise:**
${sp.promise_section || ""}

**What's Included:**
${spIncluded || "- [What's included]"}

**Who Is This For:**
${sp.who_is_this_for || ""}

**Price:** ${sp.price_display || "[Your Price]"}

**CTA Button:** ${sp.cta_button || ""}

**Guarantee:**
${sp.guarantee || ""}

${spFaq ? `**FAQ:**\n${spFaq}` : ""}
`.trim();

  // ── 4. Thank-You / Tripwire ─────────────────────────────────────
  const tw = pkg.thank_you_tripwire || {};
  const tripwireContent = `
**Thank You Message:**
${tw.thank_you_message || ""}

**Tripwire Headline:** ${tw.tripwire_headline || ""}

**Tripwire Description:**
${tw.tripwire_description || ""}

**Special Price:** ${tw.tripwire_price || "[Your Special Price]"}

**Tripwire CTA:** ${tw.tripwire_cta || ""}

**No-thanks link text:** ${tw.no_thanks_link || "No thanks, just send me my freebie."}
`.trim();

  // ── 5. Ad Package (link to existing) ────────────────────────────
  const adPkg = pkg.ad_package || {};
  const adContent = `
${adPkg.product_title ? `**Product:** ${adPkg.product_title}\n` : ""}
${adPkg.goal_label ? `**Goal:** ${adPkg.goal_label}\n` : ""}
A full ad package was generated including:
${(adPkg.short_video_scripts || []).length ? `- ${adPkg.short_video_scripts.length} short video script(s)\n` : ""}
${(adPkg.pinterest_pins || []).length ? `- ${adPkg.pinterest_pins.length} Pinterest pin(s)\n` : ""}
${(adPkg.facebook_posts || []).length ? `- ${adPkg.facebook_posts.length} Facebook post(s)\n` : ""}
${(adPkg.youtube_thumbnails || []).length ? `- ${adPkg.youtube_thumbnails.length} YouTube thumbnail idea(s)\n` : ""}
${adPkg.email_promo?.length ? `- ${adPkg.email_promo.length} email promo(s)\n` : ""}
${adPkg.seven_day_plan?.days?.length ? `- 7-day social media plan\n` : ""}
*See the Launch Package ZIP for the full text export of all ad copy.*
`.trim();

  // ── 6. Email Sequence ────────────────────────────────────────────
  const es = pkg.email_sequence || {};
  const emailContent = ((es.emails || [])).map((e, i) =>
    `**Email ${i + 1}: ${e.subject || "Untitled"}**\n\n${e.body || ""}`
  ).join("\n\n---\n\n");

  // ── 7. Delivery Checklist ────────────────────────────────────────
  const deliveryContent = (pkg.delivery_checklist || "").replace(/^/gm, "").trim();

  // ── 8. Launch Checklist ─────────────────────────────────────────
  const launchContent = (pkg.launch_checklist || "").replace(/^/gm, "").trim();

  // ── Assemble page ────────────────────────────────────────────────
  out.innerHTML = `
    <div class="space-y-5">
      <div class="rounded-2xl border border-amber-300 bg-amber-50 p-5 flex items-start gap-3">
        <span class="text-2xl">🚀</span>
        <div>
          <h2 class="text-lg font-bold text-amber-900">Launch Package Ready!</h2>
          <p class="text-sm text-amber-800 mt-1">All 8 sections generated for <strong>${escapeHtml(pkg.product_title || "your product")}</strong>. Download the ZIP to get all files with editable copy.</p>
          <button id="_dlLaunchPkg" class="mt-3 rounded-xl bg-amber-600 hover:bg-amber-700 text-white text-sm font-semibold px-4 py-2 transition">
            Download Launch Package ZIP
          </button>
        </div>
      </div>

      ${section("🎁", "1. Freebie Builder", freebieContent)}
      ${section("📧", "2. Opt-In Page Copy", optinContent)}
      ${section("💰", "3. Sales Page Copy", salesContent)}
      ${section("🤝", "4. Thank-You Page / Tripwire", tripwireContent)}
      ${section("📱", "5. Ad Package", adContent)}
      ${section("📬", "6. Email Follow-Up Sequence", emailContent || "_No email sequence generated._")}
      ${section("📦", "7. Delivery Checklist", deliveryContent || "_No delivery checklist._")}
      ${section("✅", "8. Launch Checklist", launchContent || "_No launch checklist._")}
    </div>`;

  // Wire ZIP download
  document.getElementById("_dlLaunchPkg").onclick = () => {
    window.location.href = `/download-launch-package/${projectId}`;
    toast("Launch Package ZIP download started!");
  };
}

// Navigate to Ad Generator with optional prefill
function goAdGenerator(funnelCtx) {
  go("ad");
  document.getElementById("adOutput").innerHTML = "";
  if (funnelCtx) prefillAdForm(funnelCtx);
}

function setBusy(id, busy) {
  const btn = document.getElementById(id);
  if (!btn) return;
  btn.disabled = busy;
}

// ---------- init ----------
document.addEventListener("click", (e) => {
  const go_ = e.target.closest("[data-go]");
  if (go_) go(go_.dataset.go);
});
document.getElementById("researchBtn").onclick = runResearch;
document.getElementById("ebookBtn").onclick = runEbook;
const ebookWsStart = document.getElementById("ebookWorkspaceStartBtn");
if (ebookWsStart) ebookWsStart.onclick = startEbookWorkspaceFromBuilder;
document.getElementById("adBtn").onclick = runTrafficContent;
document.getElementById("factoryBtn").onclick = runProduct;
document.getElementById("factoryReset").onclick = resetFactory;
document.querySelectorAll("[data-start]").forEach((b) => {
  b.onclick = () => showMarketStep(b.dataset.start);
});
document.querySelectorAll("[data-market-back]").forEach((b) => {
  b.onclick = () => showMarketStep("chooser");
});
document.getElementById("ownContinueBtn").onclick = runOwnDiscover;
document.getElementById("findBtn").onclick = runDiscover;
document.querySelectorAll("[data-yt-mode]").forEach((b) => {
  b.onclick = () => setYtMode(b.dataset.ytMode);
});
document.getElementById("ytAnalyzeBtn").onclick = runYtAnalyze;
document.getElementById("ytSearchBtn").onclick = runYtSearch;
document.getElementById("planBtn").onclick = runPlan;
document.getElementById("planClear").onclick = clearPlanForm;
document.getElementById("planSource").addEventListener("change", (e) => {
  planLineageId = null;
  const proj = planResearchCache.find((p) => String(p.id) === e.target.value);
  if (proj) prefillPlanFromResearch(proj);
});
document.getElementById("researchInput").addEventListener("keydown", (e) => { if (e.key === "Enter") runResearch(); });
document.getElementById("pubGenerateBtn").onclick = runPublishingPreview;
document.getElementById("pubSaveBtn").onclick = savePublishingLayout;
document.getElementById("pubSource").addEventListener("change", (e) => {
  const proj = pubState.projects.find((p) => String(p.id) === e.target.value);
  if (proj) prefillPubDetails(proj);
});

// ---------- Cover Editor ----------

/**
 * Open the full-page cover editor for a crossword or word search product.
 * Loads the current project data and navigates to the /cover-editor page.
 */
async function openCoverEditor(d) {
  const projectId = d._project_id;
  if (!projectId) {
    toast("Save the project first to edit the cover.", "error");
    return;
  }
  try {
    const project = await api(`/projects/${projectId}`);
    const data = project.data || d;
    const productType = data.product_type || d.product_type || "crossword";
    const packageId = data.package_id || d.package_id || "";
    // Navigate to the cover editor page
    window.location.href = `/cover-editor?project_id=${projectId}`;
  } catch (err) {
    toast("Could not load project for cover editing: " + err.message, "error");
  }
}

buildNav();

// Deep-link return from Cover Editor: /?view=factory&project_id=123
(async function bootFromQuery() {
  try {
    const params = new URLSearchParams(window.location.search || "");
    const view = (params.get("view") || "").trim();
    const pid = params.get("project_id");
    if (!view && !pid) {
      go("dashboard");
      return;
    }
    if (view) go(view);
    else go("dashboard");
    if (pid && (view === "factory" || !view)) {
      const project = await api(`/projects/${pid}`);
      if (project) openProject(project);
    }
    // Clean query so refresh doesn't re-open forever
    if (window.history && window.history.replaceState) {
      window.history.replaceState({}, "", window.location.pathname || "/");
    }
  } catch (e) {
    go("dashboard");
  }
})();
