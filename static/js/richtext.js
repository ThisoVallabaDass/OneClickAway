const INLINE = [
  [/^`([^`\n]+)`/, { code: 1 }],
  [/^\[([^\]\n]+)\]\((https?:\/\/[^\s)]+|mailto:[^\s)]+)\)/, "link"],
  [/^<u>([\s\S]+?)<\/u>/, { underline: 1 }],
  [/^\+\+(?!\s)([\s\S]*?)(?<!\s)\+\+/, { underline: 1 }],
  [/^~~(?!\s)([\s\S]*?)(?<!\s)~~/, { strike: 1 }],
  [/^\*\*(?!\s)([\s\S]*?)(?<!\s)\*\*/, { bold: 1 }],
  [/^__(?!\s)([\s\S]*?)(?<!\s)__(?!\w)/, { bold: 1, word: 1 }],
  [/^\*(?!\s)([^*\n]*?)(?<!\s)\*/, { italic: 1 }],
  [/^_(?!\s)([^_\n]*?)(?<!\s)_(?!\w)/, { italic: 1, word: 1 }],
];
export function inlineRuns(text, style) {
  style = style || {};
  const out = [];
  let buffer = "";
  const flush = () => {
    if (buffer) {
      out.push(Object.assign({}, style, { text: buffer }));
      buffer = "";
    }
  };
  for (let i = 0; i < text.length; ) {
    const rest = text.slice(i);
    const escaped = /^\\([*_~`+[\]<>\\#])/.exec(rest);
    if (escaped) {
      buffer += escaped[1];
      i += escaped[0].length;
      continue;
    }
    let taken = false;
    for (const [pattern, effect] of INLINE) {
      const m = pattern.exec(rest);
      if (!m || !m[1]) continue;
      if (effect !== "link" && effect.word && i && /\w/.test(text[i - 1]))
        continue;
      flush();
      if (effect === "link")
        out.push.apply(
          out,
          inlineRuns(
            m[1],
            Object.assign({}, style, { underline: 1, link: m[2] }),
          ),
        );
      else if (effect.code)
        out.push(Object.assign({}, style, { code: 1, text: m[1] }));
      else
        out.push.apply(out, inlineRuns(m[1], Object.assign({}, style, effect)));
      i += m[0].length;
      taken = true;
      break;
    }
    if (!taken) {
      buffer += text[i];
      i++;
    }
  }
  flush();
  return out.filter((r) => r.text);
}
function parseItem(item) {
  const body = String(item).replace(/\t/g, "  ");
  const level = Math.min(
    Math.floor((body.length - body.replace(/^ +/, "").length) / 2),
    2,
  );
  let payload = body.trim(),
    role = "bullet";
  const sub = /^#{1,6}\s*(.*)$/.exec(payload),
    quote = /^>\s?(.*)$/.exec(payload);
  if (sub) {
    role = "subheading";
    payload = sub[1].trim();
  } else if (quote) {
    role = "quote";
    payload = quote[1].trim();
  }
  return { role: role, level: level, runs: inlineRuns(payload) };
}
export function previewLine(item) {
  const block = parseItem(item);
  const line = document.createElement("div");
  line.className = "pv pv-" + block.role + " pv-l" + block.level;
  for (const run of block.runs) {
    let node = document.createTextNode(run.text);
    const enclose = (tag) => {
      const el = document.createElement(tag);
      el.append(node);
      node = el;
    };
    if (run.code) enclose("code");
    if (run.strike) enclose("s");
    if (run.italic) enclose("em");
    if (run.bold) enclose("strong");
    if (run.underline) enclose("u");
    if (run.link) node.title = run.link;
    line.append(node);
  }
  if (!block.runs.length) line.append(document.createTextNode("\u00a0"));
  return line;
}
export function renderPreview(target, items) {
  target.replaceChildren();
  for (const item of items) target.append(previewLine(item));
}
