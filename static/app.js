import { initAI } from "./js/ai-workflow.js";
import { drawStoryboard } from "./js/storyboard.js";
import { api, job, pendingJob, pollJob } from "./js/api.js";
import { renderPreview } from "./js/richtext.js";
const runJob = (path, body) => job(path, body, showProgress);
const $ = (id) => document.getElementById(id);
let current = null,
  busy = false,
  stale = false,
  humanTouch = true,
  pictures = [],
  uploadBusy = false;
let progressTimer = null,
  startedAt = 0,
  lastContact = 0,
  lastState = {},
  returningFrom = "",
  saveTimer = null,
  reviewView = "storyboard";
const DRAFT_KEY = "kaartech-studio-draft-v1";
const SAVED_FIELDS = [
  "prompt",
  "content",
  "ai-slides",
  "ai-lines",
  "typography",
  "effects",
  "unique",
  "agenda",
  "complete-story",
  "dividers",
  "images",
  "ai",
  "draft",
];
function message(text) {
  $("progress").textContent = text;
}
function error(e) {
  $("error").textContent = e.message;
  $("error").hidden = false;
  if (busy) showProgress({ status: "error", message: e.message });
  message("");
}
function invalidate() {
  stale = true;
  $("step-create").classList.remove("active");
  $("download").hidden = true;
  $("export").disabled = true;
  if (current)
    $("review-hint").textContent =
      "Content or settings changed. Choose Review slides to update this outline.";
  saveDraft();
}
function lock(on) {
  document
    .querySelectorAll(".story-card,.view-switch button")
    .forEach((el) => (el.disabled = on));
  busy = on;
  $("editor-fields").disabled = on;
  document
    .querySelectorAll("#outline input,#outline textarea,#outline button")
    .forEach((el) => (el.disabled = on));
  $("export").disabled = on || !current || stale;
  document.querySelectorAll("header button").forEach((b) => (b.disabled = on));
  $("generator").setAttribute("aria-busy", String(on));
  clearInterval(progressTimer);
  if (on) {
    $("error").hidden = true;
    message("");
    startedAt = Date.now();
    lastContact = Date.now();
    $("loading").hidden = false;
    showProgress({
      stage: "starting",
      message: "Sending your request to the local generator…",
    });
    progressTimer = setInterval(updateClock, 1000);
  } else {
    updateClock();
    saveDraft();
  }
}
function updateClock() {
  if (!startedAt) return;
  const seconds = Math.floor((Date.now() - startedAt) / 1000);
  $("loading-time").textContent =
    seconds < 60
      ? `${seconds}s elapsed`
      : `${Math.floor(seconds / 60)}m ${seconds % 60}s elapsed`;
  const gap = Math.floor((Date.now() - lastContact) / 1000);
  $("loading-connection").textContent = !busy
    ? ""
    : gap > 5
      ? `Waiting for server update (${gap}s)`
      : lastState.seconds_since_update > 15
        ? "Server connected · still working on this step"
        : "Live updates connected";
}
function showProgress(s) {
  lastState = s;
  lastContact = Date.now();
  const labels = {
    starting: "Starting",
    queued: "Waiting in queue",
    chunking: "Organizing your content",
    classification: "Organizing topics",
    layout: "Designing slides",
    images: "Finding a picture",
    export: "Building PowerPoint",
    packaging: "Packaging your file",
    validation: "Checking your presentation",
    outline: "Outline ready",
    preparing: "Preparing your presentation",
  };
  const done = s.status === "done",
    failed = s.status === "error";
  $("loading").dataset.state = failed ? "error" : done ? "done" : "running";
  $("loading-step").textContent = failed
    ? "Unable to complete"
    : done
      ? "Complete"
      : labels[s.stage] || "Preparing your presentation";
  $("loading-action").textContent = s.message || "";
  $("loading-topic").textContent = [
    s.current && s.total ? `Slide ${s.current} of ${s.total}` : "",
    s.title || "",
  ]
    .filter(Boolean)
    .join(" · ");
  const bar = $("loading-bar");
  if (done) bar.value = 100;
  else if (failed) bar.value = 0;
  else if (s.current && s.total)
    bar.value = Math.max(0, Math.min(99, ((s.current - 1) / s.total) * 100));
  else bar.removeAttribute("value");
  bar.setAttribute(
    "aria-valuetext",
    done
      ? "Complete"
      : failed
        ? "Stopped"
        : s.current && s.total
          ? `Building slide ${s.current} of ${s.total}`
          : "Working; total progress not yet available",
  );
  updateClock();
}
function design() {
  return {
    typography: $("typography").value,
    effects: $("effects").value,
    unique_layouts: $("unique").checked,
    section_dividers: $("dividers").checked,
    agenda: $("agenda").checked,
    complete_story: $("complete-story").checked,
    images: $("images").checked,
    human_touch: humanTouch,
  };
}
function countWords() {
  const t = $("content").value.trim();
  $("content-count").textContent = (t ? t.split(/\s+/).length : 0) + " words";
}
$("prompt").addEventListener("input", invalidate);
$("content").addEventListener("input", () => {
  invalidate();
  countWords();
});
for (const id of [
  "typography",
  "effects",
  "unique",
  "agenda",
  "complete-story",
  "dividers",
  "images",
  "ai",
  "draft",
])
  $(id).addEventListener("change", invalidate);
$("human-touch").onclick = () => {
  humanTouch = !humanTouch;
  $("human-touch").setAttribute("aria-pressed", String(humanTouch));
  $("human-state").textContent = humanTouch ? "On" : "Off";
  $("human-description").textContent = humanTouch
    ? "Original KaarTech layouts, a clear story, and carefully fitted content."
    : "Classic mode uses the original company template collection.";
  invalidate();
};
$("generator").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (busy || uploadBusy) return;
  lock(true);
  try {
    if (pictures.some((p) => !p.target.trim()))
      throw new Error("Add a slide heading for each picture in Add pictures.");
    current = await runJob("/api/plan", {
      prompt: $("prompt").value,
      content: $("content").value,
      use_ai: $("ai").checked,
      allow_draft: $("draft").checked,
      design: design(),
      pictures,
    });
    stale = false;
    render();
    message(
      "Outline ready. Review and edit your slides, then generate your PowerPoint.",
    );
  } catch (e) {
    error(e);
  } finally {
    lock(false);
  }
});
const STYLE_NAMES = {
  catalog: "Service comparison",
  grouped: "Grouped explanation",
  cover: "Opening slide",
  closing: "Closing slide",
  section: "Section title",
  agenda: "Overview",
  reading: "Clear text layout",
  focus: "One main idea",
  comparison: "Side-by-side comparison",
  steps: "Step-by-step explanation",
  image: "Picture and text",
  table: "Editable table",
  diagram: "Editable diagram",
  content: "Topic overview",
  timeline: "Roadmap",
  process: "Process",
  architecture: "Architecture",
  pointers: "Key points",
  goals: "Goals",
  metrics: "Measures",
};
const COMPANY_NAMES = {
  13: "Content layout",
  14: "Table",
  16: "Two columns",
  17: "Named comparison",
  19: "Picture and text",
  20: "Architecture",
  35: "Agenda",
  69: "Timeline",
  77: "Three concepts",
  87: "Lifecycle",
  97: "Four key points",
  99: "Six key points",
  104: "Four cards",
  119: "Four service panels",
  153: "Five pillars",
  170: "Closing",
  180: "Cover",
};
function companyStyle(s) {
  return (
    "KaarTech · " + (COMPANY_NAMES[s.template?.number] || "Company template")
  );
}
function edited() {
  renderStoryboard();
  $("download").hidden = true;
  $("review-hint").textContent =
    "Your edits will be included when you generate PowerPoint.";
  saveDraft();
}
function render() {
  $("empty").hidden = true;
  $("step-review").classList.add("active");
  $("outline-title").textContent = "Make it yours";
  $("slidecount").textContent = current.slides.length + " slides";
  $("outline").replaceChildren();
  $("warnings").replaceChildren();
  for (const w of current.warnings) {
    const p = document.createElement("p");
    p.className = "notice";
    p.textContent = w;
    $("warnings").append(p);
  }
  current.slides.forEach((s, i) => {
    const row = document.createElement("details");
    row.className = "slide";
    row.open = i === (current.slides.length > 2 ? 1 : 0);
    const summary = document.createElement("summary");
    summary.className = "slide-summary";
    const n = document.createElement("span");
    n.className = "number";
    n.textContent = String(i + 1).padStart(2, "0");
    const name = document.createElement("strong");
    name.textContent = s.title;
    summary.append(n, name);
    row.append(summary);
    const wrap = document.createElement("div");
    wrap.className = "slide-body";
    const t = document.createElement("input");
    t.value = s.title;
    t.maxLength = 120;
    t.setAttribute("aria-label", `Slide ${i + 1} title`);
    t.oninput = () => {
      s.title = t.value;
      name.textContent = t.value;
      edited();
    };
    wrap.append(t);
    if (!["cover", "closing", "section"].includes(s.kind)) {
      const b = document.createElement("textarea");
      b.value = s.items.join("\n");
      b.maxLength = 4000;
      b.setAttribute("aria-label", `Slide ${i + 1} content`);
      const shown = document.createElement("div");
      shown.className = "preview-body";
      renderPreview(shown, s.items);
      b.oninput = () => {
        s.items = b.value.split("\n").filter((x) => x.trim());
        if (s.diagram) s.diagram = null;
        if (s.kind === "table")
          s.table = s.items.map((line) =>
            line
              .replace(/^\||\|$/g, "")
              .split("|")
              .map((cell) => cell.trim()),
          );
        renderPreview(shown, s.items);
        edited();
      };
      wrap.append(b, shown);
    }
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = companyStyle(s);
    wrap.append(meta);
    if (s.image) {
      const img = document.createElement("img");
      img.src = "/api/images/" + s.image.id;
      img.alt = s.image.title;
      img.className = "slide-image";
      wrap.append(img);
    }
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "text-button";
    remove.textContent = "Remove slide";
    remove.setAttribute("aria-label", `Remove slide ${i + 1}`);
    remove.disabled = current.slides.length <= 2;
    remove.onclick = () => {
      if (busy || current.slides.length <= 2) return;
      current.slides.splice(i, 1);
      render();
      edited();
    };
    wrap.append(remove);
    row.append(wrap);
    row.addEventListener("toggle", () => {
      if (row.open)
        for (const other of $("outline").children)
          if (other !== row) other.open = false;
    });
    $("outline").append(row);
  });
  renderStoryboard();
  setReviewView(reviewView);
  $("review-hint").textContent =
    "Content preview · Select a slide to edit. Generate when ready.";
  $("download").hidden = true;
}
function setReviewView(view) {
  reviewView = view;
  $("storyboard").hidden = !current || view !== "storyboard";
  $("outline").hidden = Boolean(current) && view !== "outline";
  $("view-storyboard").setAttribute(
    "aria-pressed",
    String(view === "storyboard"),
  );
  $("view-outline").setAttribute("aria-pressed", String(view === "outline"));
}
$("view-storyboard").onclick = () => {
  setReviewView("storyboard");
  saveDraft();
};
$("view-outline").onclick = () => {
  setReviewView("outline");
  saveDraft();
};
function renderStoryboard() {
  drawStoryboard($("storyboard"), current?.slides, companyStyle, (i) => {
    if (busy) return;
    setReviewView("outline");
    const rows = $("outline").children;
    for (const [j, row] of [...rows].entries()) row.open = j === i;
    rows[i]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    saveDraft();
  });
}
$("export").onclick = async () => {
  if (busy || !current || stale) return;
  lock(true);
  $("download").hidden = true;
  try {
    const r = await runJob("/api/generate", current);
    if (r.outline) {
      current = r.outline;
      render();
    }
    $("download").href = r.download;
    $("download").textContent = `Download PowerPoint · ${r.slide_count} slides`;
    $("download").hidden = false;
    $("step-create").classList.add("active");
    message(
      r.adjusted_slides
        ? "Your PowerPoint is ready. Edited slides were re-fitted; the updated outline is shown above."
        : "Your PowerPoint is ready to download.",
    );
  } catch (e) {
    error(e);
  } finally {
    lock(false);
  }
};
async function health() {
  try {
    const h = await api("/api/health");
    $("health").textContent =
      `${h.catalog.slides || 0} company slide examples available. ${h.ai.chat_ready ? "Optional local AI is ready." : "You can create slides using your own content or any AI website."}`;
  } catch {
    $("health").textContent =
      "Start the local server to load the company slide library.";
  }
}
$("searchbtn").onclick = async () => {
  try {
    const r = await api(
      "/api/templates/search?q=" + encodeURIComponent($("search").value),
    );
    $("matches").replaceChildren();
    for (const [i, t] of r.results.entries()) {
      const el = document.createElement("div");
      el.className = "match";
      const title = document.createElement("strong");
      title.textContent =
        (STYLE_NAMES[t.category] || "Company slide design") + " " + (i + 1);
      const detail = document.createElement("small");
      detail.textContent =
        ({
          comparison: "Present two approaches next to each other.",
          timeline: "Show milestones in a clear order.",
          process: "Explain how a process works.",
          goals: "Give priorities a clear visual structure.",
          content: "Give one subject space to stand out.",
          table: "Make rows and columns easy to compare.",
        }[t.category] ||
          "A company design for presenting your ideas clearly.") +
        " " +
        (t.auto_supported
          ? "Available for automatic design."
          : "From the company reference collection.");
      el.append(title, detail);
      $("matches").append(el);
    }
    if (!r.results.length)
      $("matches").textContent =
        "No styles found. Try “roadmap”, “comparison”, or “goals”.";
  } catch (e) {
    $("matches").textContent = e.message;
  }
};
$("search").addEventListener("keydown", (e) => {
  if (e.key === "Enter") $("searchbtn").click();
});
document
  .querySelectorAll("[data-dialog]")
  .forEach((b) => (b.onclick = () => $(b.dataset.dialog).showModal()));
document
  .querySelectorAll("[data-close]")
  .forEach((b) => (b.onclick = () => b.closest("dialog").close()));
document.querySelectorAll("[data-search]").forEach(
  (b) =>
    (b.onclick = () => {
      $("search").value = b.dataset.search;
      $("searchbtn").click();
    }),
);
function renderPictures() {
  $("picture-count").textContent = pictures.length
    ? `${pictures.length} added`
    : "Optional";
  $("picture-list").replaceChildren();
  pictures.forEach((p, i) => {
    const row = document.createElement("div");
    row.className = "picture-row";
    const img = document.createElement("img");
    img.src = "/api/images/" + p.image.id;
    img.alt = p.image.title;
    const group = document.createElement("div");
    const name = document.createElement("small");
    name.textContent = p.image.title;
    const label = document.createElement("label");
    label.textContent = "Slide heading";
    const input = document.createElement("input");
    input.value = p.target;
    input.maxLength = 120;
    input.placeholder = "e.g. Pilot roadmap";
    input.setAttribute("aria-label", `Slide heading for ${p.image.title}`);
    input.oninput = () => {
      p.target = input.value;
      invalidate();
    };
    label.append(input);
    group.append(name, label);
    const remove = document.createElement("button");
    remove.textContent = "×";
    remove.setAttribute("aria-label", `Remove ${p.image.title}`);
    remove.onclick = () => {
      pictures.splice(i, 1);
      renderPictures();
      invalidate();
    };
    row.append(img, group, remove);
    $("picture-list").append(row);
  });
}
$("picture-files").onchange = async (e) => {
  uploadBusy = true;
  $("plan").disabled = true;
  $("upload-status").textContent = "Adding pictures…";
  try {
    for (const file of e.target.files) {
      if (pictures.length >= 12)
        throw new Error("You can add up to 12 pictures.");
      if (file.size > 8000000) throw new Error(`${file.name} is over 8 MB.`);
      const r = await fetch(
        "/api/images/upload?name=" + encodeURIComponent(file.name),
        { method: "POST", body: file, signal: AbortSignal.timeout(30000) },
      );
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail);
      pictures.push({ image: data, target: "" });
      renderPictures();
      invalidate();
    }
    $("upload-status").textContent =
      "Added. Enter the matching slide heading for each picture.";
  } catch (e) {
    $("upload-status").textContent = e.message;
  } finally {
    uploadBusy = false;
    $("plan").disabled = busy;
    e.target.value = "";
  }
};
initAI({
  $,
  api,
  isBusy: () => busy || uploadBusy,
  clearReturn: () => {
    returningFrom = "";
  },
  saveDraft,
  message,
  error,
  invalidate,
  countWords,
});
function saveDraft() {
  try {
    const fields = {};
    for (const id of SAVED_FIELDS) {
      const el = $(id);
      fields[id] = el.type === "checkbox" ? el.checked : el.value;
    }
    localStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({
        version: 4,
        reviewView,
        fields,
        humanTouch,
        pictures,
        current,
        stale,
        returningFrom,
        download: $("download").hidden
          ? null
          : {
              href: $("download").getAttribute("href"),
              text: $("download").textContent,
            },
      }),
    );
    $("save-status").textContent = "Draft saved in this browser";
    return true;
  } catch {
    $("save-status").textContent = "Draft could not be saved";
    return false;
  }
}
function restoreDraft() {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
    if (!d || ![1, 2, 3, 4].includes(d.version)) return;
    for (const id of SAVED_FIELDS) {
      if (d.version < 4 && ["agenda", "complete-story"].includes(id)) continue;
      if (d.fields?.[id] === undefined) continue;
      const el = $(id);
      if (el.type === "checkbox") el.checked = Boolean(d.fields[id]);
      else el.value = d.fields[id];
    }
    reviewView = d.reviewView === "outline" ? "outline" : "storyboard";
    humanTouch = d.humanTouch !== false;
    $("human-touch").setAttribute("aria-pressed", String(humanTouch));
    $("human-state").textContent = humanTouch ? "On" : "Off";
    $("human-description").textContent = humanTouch
      ? "Original KaarTech layouts, a clear story, and carefully fitted content."
      : "Classic mode uses the original company template collection.";
    const engineUpdated =
      d.current?.slides?.length && (d.current.template_engine || 0) < 8;
    pictures = Array.isArray(d.pictures) ? d.pictures : [];
    renderPictures();
    countWords();
    stale = Boolean(d.stale) || d.version < 4 || Boolean(engineUpdated);
    returningFrom = d.returningFrom || "";
    if (d.current?.slides?.length && Array.isArray(d.current.warnings)) {
      current = d.current;
      render();
      $("export").disabled = stale;
      if (stale)
        $("review-hint").textContent =
          d.version < 4 || engineUpdated
            ? "The design engine has been updated. Choose Review slides to apply the improvements. Your content and edits are saved."
            : "Content or settings changed. Choose Review slides to update this outline.";
      if (
        !stale &&
        d.download &&
        /^\/api\/download\/[a-f0-9]{32}$/.test(d.download.href)
      ) {
        $("download").href = d.download.href;
        $("download").textContent = d.download.text;
        $("download").hidden = false;
      }
    }
  } catch {
    $("save-status").textContent = "Saved draft could not be restored";
  }
}
document.addEventListener("input", () => {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveDraft, 250);
});
document.addEventListener("change", () => {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveDraft, 0);
});
window.addEventListener("pagehide", saveDraft);
window.addEventListener("pageshow", () => {
  if (returningFrom) {
    message(
      `Paste your AI answer into Your content, then choose Review slides.`,
    );
    returningFrom = "";
    saveDraft();
  }
});
health();
$("example").onclick = () => {
  $("prompt").value = "Generative AI for enterprise teams";
  $("content").value =
    `# Understanding the technology\n\n## Generative AI overview\nGenerative AI creates text, images, and code from patterns learned during training. Teams should review outputs for accuracy before use.\n\n### What changes for a team\n- Drafting starts from a **generated first version** rather than a blank page.\n  - Reviewers still decide what is published.\n  - Approved sources remain the reference.\n\n### What does not change\n> Accountability for a published document stays with the person who publishes it.\n\n## Traditional AI versus generative AI\n- Traditional AI: predicts a label or value from structured inputs.\n- Generative AI: produces new content from instructions and context.\n\n## Business use cases\n- Support teams can draft replies using approved knowledge articles.\n- Developers can generate initial code and test ideas.\n- Employees can summarize long internal documents.\n- Marketing teams can explore draft copy for review.\n\n# Putting it into practice\n\n## Pilot roadmap\n- Discovery: choose a narrow use case and a business owner.\n- Preparation: curate approved data and define evaluation criteria.\n- Pilot: test with a small group and record errors.\n- Review: compare results with the current workflow before expansion.\n\n## RAG architecture\nUser query -> Query embedding -> Vector retrieval -> Prompt assembly -> Language model -> Reviewed answer\n\n## Risks and controls\n### Accuracy\n- Inaccurate outputs: require source checks and human review.\n- ~~Unverified claims~~ must not reach a published deck.\n\n### Data handling\n- Sensitive data: restrict access and follow company data policies.\n- Keep prompts free of ++personally identifiable information++.\n\n## Review checklist\n| Check | Owner | Evidence |\n|---|---|---|\n| Factual accuracy | Author | Linked source |\n| Data handling | Reviewer | Policy reference |\n| Tone and branding | Reviewer | Approved template |\n\n## Success measures\nTrack time saved, reviewer acceptance, and factual error rates. Establish a baseline before the pilot. No performance improvement is assumed in advance.`;
  invalidate();
  countWords();
};

restoreDraft();
saveDraft();

async function resumePendingJob() {
  const saved = pendingJob();
  if (!saved) return;
  lock(true);
  try {
    const result = await pollJob(saved.id, showProgress);
    current = saved.path === "/api/generate" ? result.outline : result;
    stale = false;
    render();
    if (saved.path === "/api/generate") {
      $("download").href = result.download;
      $("download").textContent =
        `Download PowerPoint · ${result.slide_count} slides`;
      $("download").hidden = false;
      $("step-create").classList.add("active");
    }
    message("Your saved job is complete.");
  } catch (e) {
    error(e);
  } finally {
    lock(false);
  }
}
resumePendingJob();
