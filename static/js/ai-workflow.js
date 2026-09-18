const PROVIDERS = {
  chatgpt: { name: "ChatGPT", url: "https://chatgpt.com/" },
  claude: { name: "Claude", url: "https://claude.ai/new" },
  gemini: { name: "Gemini", url: "https://gemini.google.com/app" },
};

export function initAI({
  $,
  api,
  isBusy,
  clearReturn,
  saveDraft,
  message,
  error,
  invalidate,
  countWords,
}) {
  function aiRequest(provider = "chatgpt") {
    const topic = $("prompt").value.trim(),
      slides = Number($("ai-slides").value),
      lines = Number($("ai-lines").value);
    if (!topic) throw new Error("Enter a presentation topic first.");
    if (!Number.isInteger(slides) || slides < 2 || slides > 30)
      throw new Error("Choose between 2 and 30 content slides.");
    return { provider, topic, slides, lines };
  }
  $("ai-menu-button").onclick = () => {
    const open = $("provider-menu").hidden;
    $("provider-menu").hidden = !open;
    $("ai-menu-button").setAttribute("aria-expanded", String(open));
  };
  function closeMenu() {
    $("provider-menu").hidden = true;
    $("ai-menu-button").setAttribute("aria-expanded", "false");
  }
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".prompt-menu")) closeMenu();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeMenu();
  });
  async function preparePrompt(provider = "chatgpt") {
    if (isBusy()) return;
    const request = aiRequest(provider);
    const cfg = PROVIDERS[provider];
    $("prompt-heading").textContent = `Prepare content with ${cfg.name}`;
    $("prompt-output").value = "";
    $("prompt-status").textContent = "Generating your prompt…";
    $("copy-generated-prompt").disabled = true;
    $("open-provider").hidden = true;
    $("prompt-dialog").showModal();
    try {
      const r = await api("/api/ai/prompt", request);
      $("prompt-output").value = r.prompt;
      $("copy-generated-prompt").disabled = false;
      $("open-provider").href = cfg.url;
      $("open-provider").dataset.provider = provider;
      $("open-provider").textContent = `Open ${cfg.name} in a new tab ↗`;
      $("open-provider").hidden = false;
      $("prompt-status").textContent =
        "Prompt ready. Copy it before opening your AI.";
    } catch (e) {
      $("prompt-status").textContent = e.message;
    }
  }
  $("copy-prompt").onclick = () => preparePrompt().catch(error);
  document.querySelectorAll("[data-provider]").forEach(
    (b) =>
      (b.onclick = () => {
        closeMenu();
        preparePrompt(b.dataset.provider).catch(error);
      }),
  );
  $("copy-generated-prompt").onclick = async () => {
    try {
      await navigator.clipboard.writeText($("prompt-output").value);
      $("prompt-status").textContent =
        "Copied. Open your AI and paste the prompt there.";
    } catch {
      $("prompt-output").focus();
      $("prompt-output").select();
      $("prompt-status").textContent =
        "Copy is blocked by your browser. Press Ctrl+C (or Command+C) to copy the selected prompt.";
    }
  };
  $("open-provider").onclick = () => {
    clearReturn();
    saveDraft();
    $("prompt-dialog").close();
    message(
      "Studio stays open here. Paste the prompt in your AI tab, then copy its answer into Your content.",
    );
    // An ordinary target=_blank link requests a new tab in the existing browser; no window features or browser process.
  };
  $("paste-content").onclick = async () => {
    $("content").focus();
    // Paste at the selection, preserving existing content unless the user selects it.
    try {
      const text = await navigator.clipboard.readText();
      const input = $("content");
      if (
        input.value.length -
          (input.selectionEnd - input.selectionStart) +
          text.length >
        60000
      )
        throw new Error("The combined content exceeds 60,000 characters.");
      input.setRangeText(text, input.selectionStart, input.selectionEnd, "end");
      invalidate();
      countWords();
      saveDraft();
      message(
        "Response pasted. Review the content, then choose Review slides.",
      );
    } catch (e) {
      message(
        e.message.includes("60,000")
          ? e.message
          : "Click Your content and press Ctrl+V (or Command+V) to paste your AI response.",
      );
    }
  };
}
