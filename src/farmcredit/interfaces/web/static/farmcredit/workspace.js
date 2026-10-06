// SPDX-License-Identifier: AGPL-3.0-only
document.addEventListener("input", (event) => {
  if (!event.target.closest("#calculation form")) return;
  document.querySelector("#evidence-details").hidden = true;
  document.querySelector("#stale-result").hidden = false;
  const reference = document.querySelector("#reference-status");
  if (reference) reference.textContent = "Inputs changed. The saved version is unchanged; calculate to compare.";
  const result = document.querySelector("#result");
  if (result && result.querySelector("#result-summary")) {
    result.hidden = true;
    document.querySelector("#stale-result").hidden = false;
  }
});
document.addEventListener("htmx:afterSwap", () => {
  const target = document.querySelector("#form-errors, #evidence-errors, #result-summary");
  if (target) target.focus();
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

const loginError = document.querySelector("#login-error");
if (loginError) loginError.focus();

window.addEventListener("pageshow", (event) => {
  if (event.persisted && document.querySelector(".sidebar")) window.location.reload();
});

const draftError = document.querySelector("#draft-error");
if (draftError) draftError.focus();
document.querySelectorAll("[data-draft-source]").forEach((link) => {
  link.addEventListener("click", () => {
    const source = document.querySelector(link.getAttribute("href"));
    if (source) {
      source.closest("details").open = true;
      source.focus();
    }
  });
});
