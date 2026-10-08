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
    const error = document.querySelector("#request-error");
    if (error) error.hidden = false;
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

// External evidence retrieval can take several seconds; show actual pending work.
document.querySelectorAll("[data-investigation-form]").forEach((form) => {
  form.addEventListener("submit", () => {
    form.querySelector("button").disabled = true;
    const status = form.querySelector("[data-investigation-status]");
    if (status) status.hidden = false;
  });
});

// One foreground POST starts work; independent reads refresh committed progress.
let investigationPoll = null;
let investigationClock = null;
let investigationRequest = null;
let investigationStarted = 0;
let investigationStopped = true;
let lastAnnouncement = "";
function setWorkspaceState(state) {
  const studio = document.querySelector(".agent-studio");
  if (!studio) return;
  studio.dataset.workspaceState = state;
  studio.querySelector("[data-studio-status]").textContent = {
    running: "Working on your request", start: "Ready when you are",
    review: "Review the recorded outcome", interrupted: "Needs your attention",
  }[state];
  studio.querySelectorAll("[data-studio-step]").forEach(step => {
    if (step.dataset.studioStep === state) step.setAttribute("aria-current", "step");
    else step.removeAttribute("aria-current");
  });
  studio.querySelector(".agent-introduction").hidden = state === "running";
  studio.querySelector(".agent-composer").hidden = state === "running";
  const nextRequest = studio.querySelector(".next-request");
  if (nextRequest) nextRequest.hidden = state !== "running" && !document.querySelector("#next-task").value;
  studio.querySelector("#agent-thread").hidden = state === "running";
  const history = studio.querySelector(".studio-history-toggle");
  if (history) {
    history.hidden = state !== "running";
    history.setAttribute("aria-expanded", "false");
    history.textContent = "Show earlier conversation";
  }
}
document.querySelector(".studio-history-toggle")?.addEventListener("click", event => {
  const thread = document.querySelector("#agent-thread");
  thread.hidden = !thread.hidden;
  event.currentTarget.setAttribute("aria-expanded", String(!thread.hidden));
  event.currentTarget.textContent = thread.hidden ? "Show earlier conversation" : "Hide earlier conversation";
});
function announceInvestigation(message) {
  if (message === lastAnnouncement) return;
  lastAnnouncement = message;
  const region = document.querySelector("#investigation-announcement");
  if (region) region.textContent = message;
}
function stopInvestigationFeedback() {
  investigationStopped = true;
  clearTimeout(investigationPoll);
  clearInterval(investigationClock);
  investigationRequest?.abort();
}
function updateInvestigationClock() {
  const box = document.querySelector("#investigation-progress");
  const elapsed = box?.querySelector("[data-elapsed]");
  if (!elapsed || box.dataset.watch !== "true") return;
  const start = box.dataset.startedAt ? Date.parse(box.dataset.startedAt) : investigationStarted;
  elapsed.textContent = `${Math.max(0, Math.floor((Date.now() - start) / 1000))}s`;
}
function investigationUnconfirmed(message) {
  stopInvestigationFeedback();
  setWorkspaceState("interrupted");
  const send = document.querySelector("[data-live-investigation] button[type=submit]");
  if (send) send.textContent = "Outcome not confirmed";
  const box = document.querySelector("#investigation-progress");
  if (!box) return;
  box.dataset.watch = "false";
  box.querySelector(".progress-spinner")?.classList.remove("progress-spinner");
  let notice = box.querySelector("[data-connection-error]");
  if (!notice) {
    notice = document.createElement("p");
    notice.dataset.connectionError = "true";
    notice.className = "form-error";
    notice.setAttribute("role", "alert");
    box.append(notice);
  }
  notice.textContent = message;
  const link = document.createElement("a");
  link.href = "/applications/";
  link.textContent = " Reopen applications to check the recorded outcome.";
  notice.append(link);
  const status = box.querySelector("[data-connection-status]");
  if (status) status.textContent = "Updates interrupted";
}
async function refreshInvestigation(url) {
  if (investigationStopped) return;
  investigationRequest = new AbortController();
  const timeout = setTimeout(() => investigationRequest?.abort(), 8000);
  try {
    const response = await fetch(url, {
      credentials: "same-origin", cache: "no-store", signal: investigationRequest.signal,
      headers: {"HX-Request": "true"},
    });
    if (investigationStopped) return;
    const redirect = response.headers.get("HX-Redirect");
    if (redirect) { stopInvestigationFeedback(); window.location.assign(redirect); return; }
    if (!response.ok) throw new Error("Progress unavailable");
    const html = await response.text();
    if (investigationStopped) return;
    const parsed = new DOMParser().parseFromString(html, "text/html");
    const next = parsed.querySelector("#investigation-progress");
    if (!next) throw new Error("Progress unavailable");
    // Preserve keyboard focus when a refresh replaces a focused link.
    const focused = document.activeElement?.closest("#investigation-progress a")?.getAttribute("href");
    // Keep HTMX's original target attached: beforeSwap bubbles from that node.
    const current = document.querySelector("#investigation-progress");
    for (const attribute of Array.from(current.attributes)) current.removeAttribute(attribute.name);
    for (const attribute of next.attributes) current.setAttribute(attribute.name, attribute.value);
    const disclosureStates = new Map(Array.from(current.querySelectorAll("details[data-progress-details]"))
      .map(detail => [detail.dataset.progressDetails, detail.open]));
    const focusedDetail = document.activeElement?.closest("details[data-progress-details]")?.dataset.progressDetails;
    const summaryFocused = document.activeElement?.tagName === "SUMMARY";
    current.innerHTML = next.innerHTML;
    current.querySelectorAll("details[data-progress-details]").forEach(detail => {
      if (disclosureStates.has(detail.dataset.progressDetails)) {
        detail.open = disclosureStates.get(detail.dataset.progressDetails);
      }
      if (summaryFocused && detail.dataset.progressDetails === focusedDetail) {
        detail.querySelector("summary")?.focus({preventScroll: true});
      }
    });
    if (focused) Array.from(current.querySelectorAll("a")).find(a => a.getAttribute("href") === focused)?.focus({preventScroll: true});
    updateInvestigationClock();
    announceInvestigation(next.querySelector("h2")?.textContent || "Investigation updated");
    if (next.dataset.watch !== "true") { stopInvestigationFeedback(); return; }
    if (!next.dataset.startedAt && Date.now() - investigationStarted > 10000) {
      investigationUnconfirmed("The server has not confirmed that this investigation started. Check the recorded outcome before retrying.");
      return;
    }
    if (Date.now() - investigationStarted > 130000) {
      investigationUnconfirmed("The time limit has passed. A completed outcome has not been confirmed.");
      return;
    }
    investigationPoll = setTimeout(() => refreshInvestigation(url), 1500);
  } catch (error) {
    if (!investigationStopped) investigationUnconfirmed("Live updates could not be refreshed. The investigation may still be running.");
  } finally { clearTimeout(timeout); }
}
document.addEventListener("htmx:beforeRequest", (event) => {
  const form = event.detail.elt;
  if (!form.matches("[data-live-investigation]")) return;
  investigationStopped = false;
  investigationStarted = Date.now();
  setWorkspaceState("running");
  const progress = document.querySelector("#investigation-progress");
  progress.hidden = false;
  document.querySelectorAll("[data-investigation-form] button").forEach(button => { button.disabled = true; });
  form.querySelector("button").textContent = "Investigation running…";
  announceInvestigation("Request sent. Waiting for the server to confirm the investigation started.");
  progress.setAttribute("tabindex", "-1");
  progress.focus({preventScroll: true});
  document.querySelector(".agent-studio")?.scrollIntoView({block: "start"});
  investigationClock = setInterval(updateInvestigationClock, 1000);
  refreshInvestigation(form.dataset.progressUrl);
});
document.addEventListener("htmx:beforeSwap", (event) => {
  if (!event.detail.requestConfig?.elt?.matches("[data-live-investigation]")) return;
  stopInvestigationFeedback();
  const progress = document.querySelector("#investigation-progress");
  if (progress) event.detail.target = progress;
  if (event.detail.xhr.status >= 400) {
    setWorkspaceState("interrupted");
    if (!document.querySelector("#next-task")?.value) saveFollowupDraft(document.querySelector("#agent-task").value);
    event.detail.shouldSwap = true;
    event.detail.isError = false;
    document.querySelectorAll("[data-investigation-form] button, [data-agent-prompt]").forEach(button => { button.disabled = false; });
    const send = document.querySelector("[data-live-investigation] button[type=submit]");
    if (send) send.textContent = "Send to agent ↑";
    const pending = document.querySelector("#pending-task");
    if (pending) pending.hidden = true;
    announceInvestigation("The server returned an error. Read the explanation below before retrying.");
  }
});
for (const eventName of ["htmx:sendError", "htmx:timeout"]) {
  document.addEventListener(eventName, (event) => {
    if (event.detail.elt.matches("[data-live-investigation]")) {
      investigationUnconfirmed("The response could not be confirmed. Inspect the recorded run before retrying.");
    }
  });
}

// Announce a completed demo update and keep keyboard users at its result.
document.addEventListener("htmx:afterSwap", (event) => {
  if (event.detail.target.id === "demo-scenario") {
    document.querySelector("#demo-result")?.focus({preventScroll: true});
  }
});

// Suggestions draft a request; only Send invokes the agent.
document.addEventListener("click", (event) => {
  const suggestion = event.target.closest("[data-agent-prompt]");
  if (!suggestion) return;
  const composer = document.querySelector("#agent-task");
  if (!composer || composer.disabled) return;
  const draft = composer.value.trim();
  const text = composer.closest(".followup-composer") && draft
    ? `${draft}\n\nFocus: ${suggestion.dataset.agentPrompt}` : suggestion.dataset.agentPrompt;
  if (text.length > composer.maxLength) {
    document.querySelector("#composer-feedback").textContent = "Your draft is unchanged. Shorten it before adding another focus (1,000 characters maximum).";
    composer.focus();
    return;
  }
  composer.value = text;
  composer.dispatchEvent(new Event("input", {bubbles: true}));
  composer.focus();
});
document.addEventListener("htmx:beforeRequest", (event) => {
  if (!event.detail.elt.matches("[data-live-investigation]")) return;
  const task = document.querySelector("#agent-task");
  const pending = document.querySelector("#pending-task");
  if (task && pending) {
    pending.querySelector("[data-pending-task]").textContent = task.value;
    pending.hidden = false;
  }
  document.querySelectorAll("[data-agent-prompt]").forEach(button => { button.disabled = true; });
});

// Native dialogs supply focus containment and Escape without custom keyboard traps.
const caseSections = ["application-records", "application-history"]
  .map(id => document.getElementById(id));
let casePanel = null;
let panelTrigger = null;
if (document.querySelector(".agent-studio") && caseSections.every(Boolean)) {
  casePanel = document.createElement("dialog");
  casePanel.className = "case-panel";
  casePanel.setAttribute("aria-labelledby", "case-panel-title");
  casePanel.innerHTML = '<header class="case-panel-header"><h2 id="case-panel-title">Case reference</h2><button type="button" class="secondary">Close</button></header>';
  document.body.append(casePanel);
  caseSections.forEach(section => casePanel.append(section));
  casePanel.querySelector("button").addEventListener("click", () => casePanel.close());
  casePanel.addEventListener("close", () => panelTrigger?.focus({preventScroll: true}));
  document.addEventListener("click", event => {
    const link = event.target.closest('a[href="#application-records"], a[href="#application-history"]');
    if (!link) return;
    event.preventDefault();
    panelTrigger = link;
    openCasePanel(document.querySelector(link.getAttribute("href")));
  });
  if (caseSections[0].open) openCasePanel(caseSections[0]);
}
function openCasePanel(target) {
  if (!casePanel || !target) return;
  caseSections.forEach(section => { section.hidden = section !== target; });
  target.open = true;
  casePanel.querySelector("h2").textContent = target.id === "application-records" ? "Application details" : "Case history";
  if (!casePanel.open) casePanel.showModal();
}

// Deep links reveal supporting details without making every panel visible by default.
function revealWorkspaceSection() {
  const id = window.location.hash.slice(1);
  if (!id) return;
  const target = id === "agent-thread"
    ? document.querySelector("#latest-exchange") || document.getElementById(id)
    : document.getElementById(id);
  if (!target) return;
  if (casePanel?.contains(target)) openCasePanel(target.closest("#application-records, #application-history"));
  let element = target;
  while (element) {
    if (element.tagName === "DETAILS") element.open = true;
    element = element.parentElement;
  }
  target.scrollIntoView({block: "start"});
  if (target.matches("textarea, input")) target.focus({preventScroll: true});
}
window.addEventListener("hashchange", revealWorkspaceSection);
revealWorkspaceSection();
document.addEventListener("click", event => {
  const link = event.target.closest('a[href^="#"]');
  if (link && link.hash === window.location.hash) revealWorkspaceSection();
});

// Optional record editors must reveal invalid fields before native validation focuses them.
document.addEventListener("invalid", event => {
  if (!event.target.closest(".intake-form")) return;
  let element = event.target.parentElement;
  while (element) {
    if (element.tagName === "DETAILS") element.open = true;
    element = element.parentElement;
  }
}, true);

// Drafting is local to this tab and case. A draft never starts or interrupts a run.
const followupStudio = document.querySelector("[data-draft-key]");
const followupTask = document.querySelector("#agent-task");
const nextTask = document.querySelector("#next-task");
const composerFeedback = document.querySelector("#composer-feedback");
function saveFollowupDraft(value) {
  if (!followupStudio) return false;
  try {
    if (value) sessionStorage.setItem(followupStudio.dataset.draftKey, value);
    else sessionStorage.removeItem(followupStudio.dataset.draftKey);
    return true;
  } catch { return false; }
}
if (followupStudio && followupTask) {
  try {
    const draft = sessionStorage.getItem(followupStudio.dataset.draftKey);
    if (draft) {
      followupTask.value = draft;
      composerFeedback.textContent = "Your unsent draft is ready. Review it, then send when you’re ready.";
    }
  } catch { /* The composer remains usable without browser storage. */ }
  followupTask.addEventListener("input", () => {
    composerFeedback.textContent = saveFollowupDraft(followupTask.value)
      ? "Draft kept in this tab · Not sent" : "Draft could not be kept. Copy it before leaving this page.";
  });
}
nextTask?.addEventListener("input", () => {
  document.querySelector("[data-next-draft-status]").textContent = saveFollowupDraft(nextTask.value)
    ? "Draft kept in this tab · Not sent" : "Draft could not be kept. Copy it before the run finishes.";
});
document.addEventListener("click", event => {
  const answer = event.target.closest("[data-answer-question]");
  if (!answer || !followupTask) return;
  event.preventDefault();
  const target = followupStudio.dataset.workspaceState === "running" ? nextTask : followupTask;
  const question = `Regarding: ${answer.dataset.answerQuestion}\nMy information (source and date): `;
  const draft = target.value.trim();
  const combined = draft ? `${draft}\n\n${question}` : question;
  if (combined.length > target.maxLength) {
    const feedback = target === nextTask ? document.querySelector("[data-next-draft-status]") : composerFeedback;
    feedback.textContent = "Your draft is unchanged. Shorten it before adding this question (1,000 characters maximum).";
  } else {
    target.value = combined;
    target.dispatchEvent(new Event("input", {bubbles: true}));
  }
  if (target === nextTask) target.closest("details").open = true;
  target.focus();
  target.scrollIntoView({block: "center", behavior: "auto"});
});
document.addEventListener("htmx:beforeRequest", event => {
  if (!event.detail.elt.matches("[data-live-investigation]")) return;
  saveFollowupDraft("");
  if (nextTask) nextTask.value = "";
});

document.querySelector("#agent-task")?.addEventListener("keydown", event => {
  if (event.key !== "Enter" || !(event.ctrlKey || event.metaKey) || event.isComposing) return;
  event.preventDefault();
  const form = event.currentTarget.form;
  const send = form.querySelector("button[type=submit]");
  if (!send.disabled) form.requestSubmit(send);
});

// Saving is explicit. Warn before leaving changed application facts behind.
const intakeForm = document.querySelector('#case-intake');
if (intakeForm) {
  let intakeDirty = false;
  intakeForm.addEventListener('input', () => {
    intakeDirty = true;
    const status = document.querySelector('#intake-save-status');
    if (status) status.textContent = 'You have unsaved changes. Save to keep them and return later.';
  });
  intakeForm.addEventListener('submit', () => { intakeDirty = false; });
  window.addEventListener('beforeunload', event => {
    if (!intakeDirty) return;
    event.preventDefault();
    event.returnValue = '';
  });
  document.querySelector('#intake-errors')?.focus();
}
