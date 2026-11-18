/**
 * Copy text, also where navigator.clipboard is missing: the async Clipboard API
 * only exists in SECURE contexts (https or localhost), so e.g. opening the app via
 * a LAN IP over http would throw. Falls back to a hidden textarea + execCommand.
 */
export async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  if (!ok) throw new Error("Copy is not supported in this browser.");
}
