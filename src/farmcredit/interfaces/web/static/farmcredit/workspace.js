// SPDX-License-Identifier: AGPL-3.0-only
document.addEventListener("input", (event) => {
  if (!event.target.closest("#calculation form")) return;
  document.querySelector("#evidence-details").hidden = true;
  document.querySelector("#stale-result").hidden = false;
  const result = document.querySelector("#result");
  if (result && result.querySelector("#result-summary")) {
    result.hidden = true;
    document.querySelector("#stale-result").hidden = false;
  }
});
document.addEventListener("htmx:afterSwap", () => {
  const target = document.querySelector("#form-errors, #evidence-errors, #result-summary");
  if (target) target.focus({ preventScroll: true });
});
for (const eventName of [
  "htmx:sendError",
  "htmx:responseError",
  "htmx:timeout",
]) {
  document.addEventListener(eventName, () => {
    document.querySelector("#request-error").hidden = false;
  });
}
