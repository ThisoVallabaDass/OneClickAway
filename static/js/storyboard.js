import { inlineRuns, previewLine } from "./richtext.js";
export function drawStoryboard(target, slides, companyStyle, onSelect) {
  target.replaceChildren();
  if (!slides) return;
  slides.forEach((s, i) => {
    const card = document.createElement("button");
    card.type = "button";
    card.className = "story-card";
    card.dataset.kind = s.composition || s.kind;
    card.setAttribute("aria-label", `Edit slide ${i + 1}: ${s.title}`);
    const top = document.createElement("div");
    top.className = "story-top";
    const num = document.createElement("span");
    num.textContent = String(i + 1).padStart(2, "0");
    const tag = document.createElement("small");
    tag.textContent = companyStyle(s);
    top.append(num, tag);
    const title = document.createElement("strong");
    title.className = "story-title";
    title.textContent = s.title;
    const content = document.createElement("div");
    content.className = "story-content";
    if (s.table) {
      const table = document.createElement("table");
      for (const values of s.table.slice(0, 4)) {
        const row = document.createElement("tr");
        for (const value of values) {
          const cell = document.createElement("td");
          cell.textContent = inlineRuns(value)
            .map((x) => x.text)
            .join("");
          row.append(cell);
        }
        table.append(row);
      }
      content.append(table);
    } else if (s.diagram) {
      const chain = document.createElement("div");
      chain.className = "story-chain";
      for (const label of s.diagram.nodes) {
        const node = document.createElement("span");
        node.textContent = label;
        chain.append(node);
      }
      content.append(chain);
    } else
      for (const item of s.items.slice(0, 3)) content.append(previewLine(item));
    if (s.image) {
      const img = document.createElement("img");
      img.src = "/api/images/" + s.image.id;
      img.alt = s.image.title;
      content.append(img);
    }
    const foot = document.createElement("span");
    foot.className = "story-edit";
    foot.textContent = "Edit slide ↗";
    card.append(top, title, content, foot);
    card.onclick = () => onSelect(i);
    target.append(card);
  });
}
