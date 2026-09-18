# OneClick-Away user guide

A local app that turns your topic and reviewed content into an editable KaarTech PowerPoint. Open **http://127.0.0.1:8765** or double-click **start.bat**.

## Presentation engine version 8: writing and readable layouts

The AI prompt now asks for an audience, distinct slide purposes, concrete explanations and a useful conclusion. It checks factual support and the relationship between points before checking the visual limits. It avoids forcing every slide into four labelled bullets. The external AI writes the refined copy; local AI remains an optional classifier that preserves supplied wording.

Explicit Markdown and numbered slide outlines retain their authored order. Unstructured notes can still use automatic topic grouping. The layout selector measures the actual body and caption font sizes, favors readable layouts, and considers the last two content layouts when choosing variety. An early layout choice no longer exhausts that design for the rest of the deck. The original KaarTech artwork stays intact.

The reviewed SAP Basis example uses three logical architecture tiers, a native DEV/QAS/PRD table, concrete administration tasks and a transport process with a quality gate. Source citations and scope qualifications are in speaker notes. Its editable source is `tests/fixtures/sap-basis-refined.md`; rebuild the application-generated version with `python scripts/rebuild_sap_basis_deck.py`. The final presentation is `output/SAP-Basis-Refined.pptx`.

Saved outlines from earlier engines request **Review slides** again so the updated layout choices apply. Your source content remains saved. Labels such as **To verify:** and **Assumption:** receive the same note-only treatment as existing unverified markers.

## The updated workflow

1. Enter **What is the presentation about?**
2. Paste your content, or use **Generate prompt** and choose **Claude**, **Gemini**, or **ChatGPT**. Choose the desired number of content slides and lines per slide. The app adds a separate cover, one concise agenda and a thank-you slide. The prompt requests an introduction and conclusion within the content slides.
3. Copy the generated prompt, choose **Open in a new tab**, and paste it into your AI. Studio stays open. Copy the answer and switch back to Studio to paste into **Your content**. You can also paste your own notes directly.
4. Leave **Human touch** on for content-aware company cards, comparisons and timelines. Both modes retain the original KaarTech template artwork.
5. Optionally choose **Add pictures**, upload PNG/JPG files, and enter the exact slide heading for each image.
6. Select **Review slides** to see the graphical storyboard. Click a card to edit the slide, or switch to **Outline**. Select **Generate PowerPoint** and download the result.

The main controls fit within a desktop viewport at 1024×768, 1280×720, 1366×768, and 1920×1080. The slide review scrolls inside its panel. Smaller screens and high browser zoom use a stacked, scrolling layout. Settings and the slide library open in dialogs.

The supplied company logo is bundled at `static/kaar-logo.png`. The UI uses red, white, warm orange accents, and dark text. Presentation font options are Modern (Bahnschrift / Segoe UI), Classic (Arial / Calibri), and Editorial (Georgia / Calibri).

## Human touch

Both modes now generate inside the actual company template collection. Human touch chooses verified original layouts for three concepts, four cards, service panels, grouped comparisons, lifecycle content and numbered timelines. Ordinary service lists do not become invented processes. Explicit architecture connections remain editable. Dense text uses the official content layouts; tables remain native PowerPoint tables.

The default story is **cover → agenda → introduction → main sections → conclusion → thank you**. Supplied introductions and conclusions are retained. Missing introductions use the supplied headings. Where the source supports known relationships across topics and delivery stages, the engine synthesizes a conclusion as editorial recommendations. Sparse or unrelated notes produce a request for an author-written conclusion; the engine never samples earlier bullets as takeaways. Main sections retain their local order; unsectioned notes are grouped into concepts, options, architecture, governance and delivery. No missing process, architecture or product claim is invented. Turn off **Organize an introduction, main sections and conclusion** to keep a minimal supplied outline. Section dividers are optional.

There is at most one agenda, generated from the final slide headings or explicit sections. It uses the original five-row, eight-row, or full-width list layout according to measured fit. Longer outlines combine adjacent topics while preserving every topic in the agenda mapping. Unused numbered rows are removed completely. The agenda updates after slide titles, section names or slide counts change during review. Manually edited agenda wording is retained when the underlying topics are unchanged.

The prompt requires concise labels and explanations that fit the original template slots. Titles and body text are measured before export. Edited slides are re-fitted when their content no longer fits the selected layout; the final outline and slide count are returned to the review panel. Suitable layouts can repeat. The generator does not add unrelated diagrams just to avoid repetition.

Exact repeated slides are removed. Repeated compute, storage, database, networking and identity sections are consolidated; explicit service names and recognized naming variants are matched while distinct descriptions remain available. Other semantic overlap remains a review warning. Statements marked as assumptions, unverified, TBD or drafts are withheld from visible slides and retained in speaker notes with a review warning. Azure, AWS, GCP and KaarTech capitalization is normalized. The application does not automatically fact-check arbitrary input.

The version 6 examples are **output/Azure-Enhanced-Corrected.pptx** and **output/Azure-Standard-Corrected.pptx**. Both are 15-slide rebuilds of the audited 20-slide deck, using the same source content including its repeated sections. The source is **output/Azure-Audited-Source.md** and the repeatable build is `python scripts/rebuild_audited_deck.py`. Earlier examples remain historical outputs.

The latest company example is **output/KaarTech-Capabilities-Upgraded.pptx**, rebuilt with `python scripts/rebuild_company_deck.py`. It contains 11 slides and an eight-topic agenda drawn from its actual content headings. The Azure examples have also been regenerated with version 7's heading, agenda and contrast rules. The earlier review document records the version 6 audit.

### Export corrections

Materialized rectangular placeholders now explicitly retain rectangle geometry, fills and borders. Corner-shaped decorative placeholders keep their artwork while editable text sits in their open panel area. This fixes disappearing card panels and text collapsing into narrow vertical columns. Old browser drafts preserve inputs but require **Review slides** after upgrading.

Every generated slide binds to its actual selected original slide layout, whose name and XML are preserved. The package validator checks that binding before saving. Materialized artwork suppresses inherited artwork to avoid duplicated or unused fields. Empty text containers are removed without removing decorative borders, unused title placeholders are dropped, and generated shape names are normalized. Speaker notes record eligibility, measured fit and the selected layout instead of a misleading list of every source page using that layout.

## Manual AI content workflow

Version 7 requires an explicit contrast such as **versus**, **Traditional/Proposed**, **Before/After** or **Pros/Cons** before choosing a comparison layout. Two related facts or named groups use ordinary content layouts. Slide headings use sentence case with protected product names and acronyms. Plain outlines with repeated short headings followed by clear body paragraphs are recovered as real slide sections, preventing one paragraph from becoming one slide titled with the deck name.

Recognized authoring footers such as **Context Chain** are removed before parsing; source lines remain in cover notes. Meaningful emoji labels, references, URLs and actual architecture connections remain content. Export checks reject authoring metadata added during review and flag dense content or points missing a subject.

Choose **Generate prompt** and select Claude, Gemini, or ChatGPT. A dialog shows the structured prompt and clear steps. **Copy prompt** copies it on request; if clipboard permission is blocked, the text is selected and the dialog explains how to use Ctrl+C / Command+C.

**Open in a new tab** uses an ordinary `target="_blank"` link with `noopener noreferrer`. It requests a separate tab in the existing browser; Studio keeps its current page and draft. The app never starts a browser process or uses popup-window features. Paste the prompt yourself, copy the AI answer, switch back to Studio, and use Ctrl+V / Command+V or **Paste AI response**.

The prompt now includes explicit visual budgets: exactly the requested number of content slides, titles up to 60 characters, up to 60 body words/400 characters per slide, and short lines and labels. AI-generated tables are limited to three columns, up to four data rows, and short cells. These conservative prompt limits keep the response manageable; the generator can also accept larger user tables and paginate them using measured cell heights.

The browser saves your topic, content, pictures, settings, review view, edited slides, and download link locally. Refresh restores the draft. Older design-engine outlines are retained but require **Review slides** again. Draft storage is specific to the browser and address (localhost and 127.0.0.1 are separate).

## Graphical workspace and table capacity

The red-and-white workspace includes original vector artwork, a compact workflow banner, and a clickable storyboard. Cards show real outline content, including small table, diagram, and picture previews; they are content previews rather than pixel-exact PowerPoint renders. Click a card to edit it in the outline. Completion becomes a compact status strip so more of the storyboard remains visible.

Table planning and export now share the same font and row-height measurements. Rows grow to fit their cells, dense tables split with repeated headers, and final pages are balanced where space allows. This fixes the supplied four-column Azure table that passed outline planning but failed during export. The regression fixture is `tests/fixtures/azure-table.md`.


Browser automation and automatic AI-response retrieval have been removed. The old `/api/ai/generate` endpoint returns an explanatory 410 response. Playwright is only a development dependency for UI tests. The application no longer starts provider browser profiles. Previously created profile files are left untouched.

## Live presentation progress

While planning or generating a deck, the slide-review panel displays a loading bar with the current backend operation, current slide and total when available, elapsed time, and connection status. A moving bar indicates work whose total is unknown. Counted stages advance using the slide count, without inventing an overall percentage. Completion collapses to a compact confirmation strip; failures show the message and re-enable the controls.

The app polls the local job endpoint for live updates. It does not monitor progress on the external AI website while you are away; that work is manual. No spinner or disabled form waits for a copied AI answer.

## Optional pictures

- PNG or JPEG, up to 8 MB each, at most 25 million pixels and 12 uploads per request.
- One picture per slide. Type the exact content heading, for example `Pilot roadmap`.
- When a heading continues, the picture goes on the first matching slide. Use distinct headings to place pictures on different slides.
- The planner reports missing headings or insufficient room instead of silently dropping an uploaded image.
- Use a text slide for a picture. Tables and diagrams need their own slide.
- Pictures remain local. Validated pixels are re-encoded with embedded metadata removed, stored by checksum, and embedded in the PowerPoint.

Audio and video are not included in this update.

## Formatting

| Input | Result |
|---|---|
| `## Slide title` or `Slide 1 — Title` | Starts a slide |
| `### Subheading` | A heading inside the slide |
| `- Point` with indentation | A point with nested detail |
| `**bold**`, `*italic*`, `++underline++` | Editable inline formatting |
| `> Quote` | Quoted callout |
| `---` | Explicit slide break |
| Markdown table rows | Editable table |
| `Input -> Retrieval -> Answer` under an architecture/process title | Editable pipeline |

Numbered slide labels may be plain text, bold, or Markdown headings. Blank lines inside a structured slide no longer create stray one-line slides. A local model cannot substitute the placeholder “Short topic title”. Conventional `##`/`###` outlines retain their hierarchy even when subheadings outnumber slides. Other heading schemes retain the existing ranked-heading parser.

The app preserves user body content during automatic planning. Review AI-generated facts before use. Pasted source documents and template text are data, not executable instructions. The AWS example was manually organized from the supplied deck and does not add new company statistics or claims.

## Setup

Python 3.12 or newer is recommended.

```powershell
python -m pip install -r requirements.txt
python scripts/run.py
```

The existing company template and SQLite index are in `data/`. To set up a fresh computer:

```powershell
python scripts/setup.py --template "C:\path\KaarTech Corporate PPT Templates - 2024 Guide.pptx" --lexical
```

For optional local AI, install Ollama and pull `qwen3:1.7b` and `nomic-embed-text`. Rebuild the index without `--lexical` to use semantic retrieval. `CHAT_MODEL`, `EMBED_MODEL`, `OLLAMA_URL`, and `KAARTECH_TEMPLATE` remain configurable. The standard HTTP server binds to loopback and rejects cross-origin writes.

## Checks

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
# With the local server running:
python tests/ui_smoke.py
node --check static/app.js
```

The Python suite covers the original template generation plus numbered AI headings, nested content, readable Human touch compositions, uploaded images, editable diagram updates, API validation, prompt formatting, and removal of browser automation. The UI smoke test uses real Chromium and local provider-page fixtures to verify separate provider tabs while Studio remains open, storyboard editing, draft restoration, clipboard fallbacks, live progress, error recovery, and real PowerPoint export. It does not send prompts to live AI accounts.

Desktop and mobile UI checks cover viewport fit, slide review, export, and invalidating a download after edits. Generated sample decks were rendered through installed PowerPoint and visually reviewed.

## Implementation

| Area | Files |
|---|---|
| Browser UI | `static/index.html`, `static/style.css`, `static/app.js` |
| Local API and background jobs | `backend/app.py` |
| Manual AI prompt construction | `backend/prompts.py` |
| Content parsing and planning | `backend/planner.py`, `backend/richtext.py` |
| Editorial consolidation and conclusions | `backend/editorial.py` |
| Original template planning and fitting | `backend/template_engine.py`, `backend/catalog.py`, `backend/design.py` |
| Editable OOXML export | `backend/exporter.py`, `backend/visuals.py` |
| Image upload and online image cache | `backend/images.py` |

The library indexes 187 source slides and 183 layouts. Both modes use verified profiles from that collection. Human touch adds subject emphasis and prefers suitable graphical or grouped layouts. Legacy composition code supports older saved decks. The library is a friendly search/browse reference, not a manual layout picker.

Version 9 stores new service decks under `output/generated/`, image assets under `data/uploads/`, and durable jobs in `data/jobs.sqlite3`. Browser drafts remain in local storage. Anonymous browser sessions own their jobs and files; queued jobs survive restarts and interrupted running jobs report failure. Files expire after seven days by default. See [Deployment](DEPLOYMENT.md) for configuration and limits.

## Optional PowerPoint visual verification

On Windows with Microsoft PowerPoint installed:

```powershell
./scripts/verify_powerpoint.ps1 -Presentation ./output/Azure-Corporate-Refined.pptx -OutputDirectory ./.build/azure-check
```

This opens only the specified deck read-only, renders every slide to PNG, and writes `verification.json` with generated-text overflow findings. It does not close other presentations. Office is needed only for this optional visual check; the generator itself writes PPTX without Office.
