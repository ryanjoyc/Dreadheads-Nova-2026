import "./styles.css";
import { screen } from "./placeholders.js";

const app = document.querySelector("#app");
app.innerHTML = `
  <p class="banner">Placeholder data. Recommendations and filled counts are not connected yet.</p>
  <div id="prep">
    <div class="bezel">
      <div class="tablet">
        <div class="status"><span class="status-time">—:—</span><span>Wi-Fi</span></div>
        <header class="bar">
          <strong>Prep</strong>
          <span class="clock"></span>
        </header>
        <div class="nav" role="tablist" aria-label="Windows">
          <button type="button" data-view="next" role="tab" aria-selected="true">Next rush</button>
          <button type="button" data-view="today" role="tab" aria-selected="false">Rest of today</button>
          <button type="button" data-view="tomorrow" role="tab" aria-selected="false">Tomorrow</button>
          <button type="button" data-view="ahead" role="tab" aria-selected="false">Further ahead</button>
          <button type="button" data-view="setup" role="tab" aria-selected="false">Setup</button>
        </div>
        <div class="sub" id="ahead-nav" hidden>
          <button type="button" data-span="week" aria-pressed="true">Week</button>
          <button type="button" data-span="month" aria-pressed="false">Month</button>
          <button type="button" data-span="next" aria-pressed="false">Next month</button>
        </div>
        <div class="sub" id="mode-nav">
          <button type="button" data-mode="dishes" aria-pressed="true">Dishes</button>
          <button type="button" data-mode="prep" aria-pressed="false">Prep list</button>
        </div>
        <div id="panel"></div>
      </div>
    </div>
  </div>
`;

const root = document.querySelector("#prep");
const panel = document.querySelector("#panel");
const aheadNav = document.querySelector("#ahead-nav");
const modeNav = document.querySelector("#mode-nav");
const clock = document.querySelector(".clock");
const statusTime = document.querySelector(".status-time");

let view = "next";
let span = "week";
let mode = "dishes";
let proposal = "pending";

function esc(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function dishRows(dishes) {
  return dishes
    .map(
      (item) =>
        `<div class="row"><span class="dish">${esc(item.name)}</span><span class="count">${esc(item.prep)}</span></div>`,
    )
    .join("");
}

function ingredientRows(items) {
  return items
    .map(
      (item) =>
        `<div class="row"><span><span class="dish">${esc(item.name)}</span><span class="uses">${esc(item.note)}</span></span><span class="count">${esc(item.amount)}</span></div>`,
    )
    .join("");
}

function prepBody(rushId) {
  const block = screen.prep[rushId];
  const title = screen.rushes[rushId].title.toLowerCase();
  let html = `<p class="meta">On hand is read from the walk-in camera.</p>`;
  if (block.now.length) html += `<h3>Start now</h3>${ingredientRows(block.now)}`;
  if (block.wait.length) html += `<h3>Wait until ${esc(title)}</h3>${ingredientRows(block.wait)}`;
  return html;
}

function rushBlock(rushId) {
  const rush = screen.rushes[rushId];
  const body = mode === "prep" ? prepBody(rushId) : dishRows(rush.dishes);
  return `<section class="rush" aria-label="${esc(rush.title)}"><h2>${esc(rush.title)} · ${esc(rush.hours)}</h2><p class="meta">${esc(rush.reason)}</p><p class="why">${esc(rush.why)}</p>${body}</section>`;
}

function proposalBlock() {
  const item = screen.proposal;
  if (proposal === "pending") {
    return `<section class="proposal" aria-label="Rush proposal"><h2>${esc(item.hours)} proposal</h2><p>${esc(item.text)}</p><p>No portions until the lead approves.</p><div class="moves"><button type="button" data-act="approve">Approve rush</button><button type="button" data-act="reject">Reject rush</button></div></section>`;
  }
  const message = proposal === "approved" ? item.approved : item.rejected;
  return `<section class="note"><p>${esc(message)}</p></section>`;
}

function paint() {
  clock.textContent = screen.clock;
  statusTime.textContent = screen.clock;
  root.querySelectorAll("[data-view]").forEach((button) => {
    button.setAttribute("aria-selected", button.dataset.view === view ? "true" : "false");
  });
  root.querySelectorAll("[data-span]").forEach((button) => {
    button.setAttribute("aria-pressed", button.dataset.span === span ? "true" : "false");
  });
  root.querySelectorAll("[data-mode]").forEach((button) => {
    button.setAttribute("aria-pressed", button.dataset.mode === mode ? "true" : "false");
  });
  aheadNav.hidden = view !== "ahead";
  modeNav.hidden = view === "ahead" || view === "setup";

  if (view === "next") {
    panel.innerHTML = `<section class="note" aria-label="Early prep"><h2>Early prep</h2><p>${esc(screen.early)}</p></section>${proposalBlock()}${rushBlock("next")}`;
    return;
  }
  if (view === "today") {
    let html = proposalBlock() + screen.today.map(rushBlock).join("");
    if (proposal === "approved") html += rushBlock(screen.proposal.rushId);
    panel.innerHTML = html;
    return;
  }
  if (view === "tomorrow") {
    panel.innerHTML = screen.tomorrow.map(rushBlock).join("");
    return;
  }
  if (view === "ahead") {
    const block = screen.ahead[span];
    panel.innerHTML = `<section class="rush" aria-label="${esc(block.label)}"><h2>${esc(block.label)}</h2><p class="meta">Sum of the rushes in this span. Not a pile to cook now.</p>${dishRows(block.dishes)}</section>`;
    return;
  }
  panel.innerHTML = `<section class="setup-block" aria-label="Standing hours"><h2>Standing hours</h2><ul>${screen.setup.hours.map((line) => `<li>${esc(line)}</li>`).join("")}</ul></section><section class="setup-block" aria-label="Prep durations"><h2>Prep durations</h2><ul>${screen.setup.durations.map((line) => `<li>${esc(line)}</li>`).join("")}</ul></section>`;
}

root.addEventListener("click", (event) => {
  const button = event.target.closest("button");
  if (!button || !root.contains(button)) return;
  if (button.dataset.view) view = button.dataset.view;
  if (button.dataset.span) span = button.dataset.span;
  if (button.dataset.mode) mode = button.dataset.mode;
  if (button.dataset.act === "approve") proposal = "approved";
  if (button.dataset.act === "reject") proposal = "rejected";
  paint();
});

paint();
