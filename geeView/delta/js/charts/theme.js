// Chart colors and type from the CSS tokens (css/tokens.css), read at draw
// time so light, dark and system themes all apply.
export function chartTheme(root = document.documentElement) {
  const cs = getComputedStyle(root);
  const t = (name, fallback) => cs.getPropertyValue(name).trim() || fallback;
  return {
    ink: t("--dz-ink", "#231d1b"),
    mute: t("--dz-mute", "#6f6259"),
    faint: t("--dz-faint", "#a2968d"),
    line: t("--dz-line", "rgba(55, 46, 44, 0.13)"),
    solid: t("--dz-solid", "#faf8f6"),
    font: t("--dz-font-body", "Roboto, sans-serif"),
    mono: t("--dz-font-mono", "monospace"),
    // series without a class or layer palette
    series: [t("--dz-teal", "#00897b"), t("--dz-orange", "#e2602a"), t("--dz-mute", "#6f6259"), t("--dz-ink", "#231d1b")],
  };
}

// Save a data URL as a file.
export function downloadUrl(url, filename) {
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
}
