import "./styles.css";

const app = document.querySelector("#app");
const state = {data:null, loading:false, error:"", source:"all", view:"next", request:0, cache:new Map(), decisions:new Map()};
let controller;
const esc = (v) => String(v ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
const count = (n) => Math.round(n).toLocaleString();
const displayDate = (day) => new Intl.DateTimeFormat("en-US",{weekday:"short",month:"short",day:"numeric",timeZone:"UTC"}).format(new Date(`${day}T12:00:00Z`));
const addDays = (day,n) => {const d=new Date(`${day}T12:00:00Z`);d.setUTCDate(d.getUTCDate()+n);return d.toISOString().slice(0,10);};
app.innerHTML = `
  <div class="demo-tools"><p class="banner">K-Station / Tartan Express · Synthetic sales demo</p>
  <details><summary>Demo settings</summary><form id="controls">
    <label>Demo date<input id="target-date" type="date" required value="2026-10-29"></label>
    <label>Time of day<input id="demo-time" type="time" required value="09:30"></label>
    <label>Day context<input id="day-context" type="text" maxlength="500" placeholder="Optional event or weather information"></label>
    <label class="agent-toggle"><input id="use-agent" type="checkbox">Use AI analysis (backend key required)</label>
    <button type="submit" class="load-button">Load day</button>
  </form><div class="demo-buttons" aria-label="Example dates"><button type="button" data-date="2026-10-25">Quiet Sunday</button><button type="button" data-date="2026-10-29">Busy Thursday</button><button type="button" data-date="2026-10-21">One-off spike</button></div>
  <div class="demo-buttons" role="group" aria-label="Sales feeds"><button type="button" data-source="all" aria-pressed="true">Both feeds</button><button type="button" data-source="doordash" aria-pressed="false">DoorDash</button><button type="button" data-source="grubhub" aria-pressed="false">Grubhub</button></div></details></div>
  <main id="prep"><div class="bezel"><div class="tablet">
    <div class="status"><span id="status-time">09:30</span><span>Synthetic sales</span></div>
    <header class="bar"><h1>K-Station</h1><span class="clock"></span></header>
    <nav class="nav" aria-label="Time horizon">
      <button type="button" data-view="next" aria-pressed="true">Next rush</button>
      <button type="button" data-view="today" aria-pressed="false">Rest of today</button>
      <button type="button" data-view="tomorrow" aria-pressed="false">Tomorrow</button>
      <button type="button" data-view="ahead" aria-pressed="false">Further ahead</button>
      <button type="button" data-view="setup" aria-pressed="false">Setup</button>
    </nav><p id="status" class="sr-only" role="status" aria-live="polite"></p><div id="panel" aria-busy="false"></div>
  </div></div></main>`;
const dateInput=document.querySelector("#target-date"), timeInput=document.querySelector("#demo-time"), panel=document.querySelector("#panel"), status=document.querySelector("#status");

function dishRows(dishes) {
  return dishes.map(d=>`<div class="row"><span class="dish">${esc(d.name)}</span><span class="count">${count(d.quantity)}</span></div>`).join("");
}
function dishList(dishes) {
  if (!dishes.length) return '<p>No dish estimates for this window.</p>';
  return dishRows(dishes.slice(0,5))+(dishes.length>5?`<details class="more-dishes"><summary>Show all ${dishes.length} dishes</summary>${dishRows(dishes.slice(5))}</details>`:"");
}
function rushName(rush) {
  const hour=Number(rush.start.slice(0,2));return hour<14?"Lunch rush":hour<17?"Afternoon rush":"Dinner rush";
}
// Explicit demo standing windows, not facts inferred from provider sales.
const standingWindows = [["11:00", "14:00"], ["17:00", "20:30"]];
const standingRush = (rush) => standingWindows.some(([start,end]) => rush.start >= start && rush.end <= end);
const decisionKey = (rush,data) => `${data.date}:${data.source}:${rush.start}:${rush.end}`;
const rushDecision = (rush,data) => state.decisions.get(decisionKey(rush,data));
function proposalBlocks(data) {
  return data.forecast.rushes.filter(r=>!standingRush(r)&&r.end>timeInput.value).map(rush=>{
    const key=esc(decisionKey(rush,data));
    const decision=rushDecision(rush,data);
    if(decision) return `<section class="note" aria-label="Rush decision" aria-live="polite"><p>${esc(rush.start)}–${esc(rush.end)} ${decision==="approved"?"approved for today. Its dish counts appear on Rest of today.":"rejected for today. It is excluded from today's rush list."}</p><button type="button" data-review="${key}">Review again</button></section>`;
    return `<section class="proposal" aria-label="Rush proposal"><h2>${esc(rush.start)}–${esc(rush.end)} proposal</h2><p>Outside the standing lunch and dinner rushes. ${esc(rush.reason || `The forecast finds extra traffic here, based on ${data.history_days} earlier matching weekdays.`)}</p><p>No dish counts until the lead approves.</p><div class="moves"><button type="button" data-approve="${key}">Approve for today</button><button type="button" data-reject="${key}">Reject rush</button></div></section>`;
  }).join("");
}
function rushBlock(rush,data,next=false) {
  return `<section class="rush" aria-label="${esc(rushName(rush))}"><h2>${esc(rushName(rush))} · ${esc(rush.start)}–${esc(rush.end)}</h2><p class="meta">${next?"Next predicted rush. ":""}${rushDecision(rush,data)==="approved"?"Approved for today. ":""}About ${count(rush.expected_orders)} orders.</p><p class="why">${esc(rush.reason || `Based on ${data.history_days} earlier matching weekdays.`)}</p>${rush.confidence ? `<p class="meta">${esc(rush.confidence)} confidence · ${Math.round(rush.consistency*100)}% historical consistency</p>` : ""}<p class="meta">Expected dish sales</p>${dishList(rush.dishes)}</section>`;
}
function noHistory(data) {
  return `<section class="note"><h2>No earlier matching weekdays</h2><p>There isn't enough sales history to estimate this day. Choose a later demo date.</p>${data.observed?`<p>${count(data.observed.orders)} orders were recorded on this date.</p>`:""}</section>`;
}
function analysisDetails(data) {
  const analysis=data.analysis;
  if(!analysis) return "";
  return `<h3>Rush analysis</h3><p>${analysis.method==="agent"?"AI-assisted":"Historical baseline"}${analysis.model?` · ${esc(analysis.model)}`:""}</p><p>${esc(analysis.summary)}</p>${analysis.flags.map(flag=>`<p class="meta">${esc(flag)}</p>`).join("")}${analysis.agent_trace.length?`<details><summary>How the agent checked the data</summary><ul>${analysis.agent_trace.map(step=>`<li>${esc(step.tool)}: ${esc(step.result)}</li>`).join("")}</ul></details>`:""}`;
}
function setup(data) {
  return `<section class="setup-block"><h2>Sales forecast</h2><p>${esc(data.reason)}</p><p>Dish counts are expected sales, rounded to whole dishes.</p><h3>Standing rushes (demo settings)</h3><p>Lunch 11:00–14:00 · Dinner 17:00–20:30. Busy windows outside these times require approval. Decisions apply only to this date and feed selection, and reset on page reload.</p><h3>History used</h3><p>${data.history_dates.map(esc).join(", ")||"No earlier matching weekdays"}</p><h3>Sales feeds</h3><p>${state.source==="all"?"DoorDash and Grubhub":esc(state.source)} · K-Station stores only.</p></section><section class="setup-block"><h2>Demo evidence</h2><p>${data.history_days?`Forecast: ${count(data.forecast.orders)} orders.`:"No forecast available."}${data.observed?` Observed on this date: ${count(data.observed.orders)} orders.`:" No observed sales for this date."}</p><p>Rushes are consecutive 15-minute slots with at least 1.5 times average active-slot traffic and at least 2 expected orders per slot.</p><p>Mock sales → PostgreSQL → sales API → analysis → tablet. The optional AI analysis uses backend-held credentials.</p>${analysisDetails(data)}<p>${esc(data.caveat)}</p></section>`;
}
function paint() {
  document.querySelectorAll("[data-view]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.view===state.view)));
  document.querySelectorAll("[data-source]").forEach(b=>b.setAttribute("aria-pressed",String(b.dataset.source===state.source)));
  document.querySelector(".clock").textContent=`${displayDate(dateInput.value)} · ${timeInput.value}`;
  document.querySelector("#status-time").textContent=timeInput.value;
  panel.setAttribute("aria-busy",String(state.loading));
  const loadButton=document.querySelector(".load-button");loadButton.disabled=state.loading;loadButton.textContent=state.loading?"Loading…":"Load day";
  status.textContent=state.loading?"Loading sales forecast…":state.error?"Forecast unavailable":state.data?`${state.data.date} · ${state.source} · ${state.data.history_days??""} comparison days`:"";
  if(state.loading){panel.innerHTML='<section class="note"><p>Loading sales forecast…</p></section>';return;}
  if(state.error){panel.innerHTML=`<section class="note" role="alert"><h2>Forecast unavailable</h2><p>${esc(state.error)}</p><button type="button" data-retry>Try again</button></section>`;return;}
  const data=state.data;if(!data)return;
  if(state.view==="ahead") {
    panel.innerHTML=`<section class="rush"><h2>Next seven days</h2><p class="meta">Expected dish sales across the week.</p>${dishList(data.dishes)}</section><section class="rush"><h2>Day by day</h2>${data.days.map(d=>`<div class="row"><span>${esc(displayDate(d.date))}<span class="uses">${d.history_days} comparison days</span></span><span class="count">${d.history_days?count(d.expected_orders):"—"}</span></div>`).join("")}<p class="meta">Expected orders. Each estimate uses only sales recorded before the demo date.</p></section>`;return;
  }
  if(state.view==="setup"){panel.innerHTML=setup(data);return;}
  if(!data.history_days){panel.innerHTML=noHistory(data);return;}
  const remaining=data.forecast.rushes.filter(r=>r.end>timeInput.value&&(standingRush(r)||rushDecision(r,data)==="approved"));
  const proposals=proposalBlocks(data);
  if(state.view==="next") {
    panel.innerHTML=proposals+(remaining.length?rushBlock(remaining[0],data,true):'<section class="note"><h2>No more predicted rushes today</h2><p>Check Tomorrow for the next day’s outlook.</p></section>');
  } else if(state.view==="today") {
    panel.innerHTML=proposals+(remaining.length?remaining.map(r=>rushBlock(r,data)).join(""):'<section class="note"><p>No more predicted rushes today.</p></section>');
  } else {
    panel.innerHTML=`<p class="meta">${esc(displayDate(data.date))}</p>`+(data.forecast.rushes.filter(standingRush).length?data.forecast.rushes.filter(standingRush).map(r=>rushBlock(r,data)).join(""):'<section class="note"><p>No predicted rush windows. Expected daily sales appear below.</p></section>')+`<section class="rush"><h2>Whole day · ${count(data.forecast.orders)} orders</h2>${dishList(data.forecast.dishes)}</section>`;
  }
}
async function load(refresh=false) {
  if(!dateInput.reportValidity()||!timeInput.reportValidity())return;
  controller?.abort();controller=new AbortController();const request=++state.request;
  const day=state.view==="tomorrow"?addDays(dateInput.value,1):dateInput.value;
  const params=new URLSearchParams({date:day});if(state.source!=="all")params.set("source",state.source);
  if(state.view!=="ahead") {
    params.set("use_agent",String(document.querySelector("#use-agent").checked));
    const context=document.querySelector("#day-context").value.trim();
    if(context)params.set("context",context);
  }
  const path=state.view==="ahead"?"/tablet/outlook":"/tablet";
  const key=`${path}?${params}`;
  state.error="";state.data=null;
  if(!refresh&&state.cache.has(key)){state.loading=false;state.data=state.cache.get(key);paint();return;}
  state.loading=true;paint();
  try {
    const res=await fetch(`/api${key}`,{signal:controller.signal});
    if(!res.ok)throw new Error(res.status===503?"K-Station sales need to be loaded. Run the demo setup, then retry.":`Sales API returned HTTP ${res.status}. Try again.`);
    const data=await res.json();
    if(path==="/tablet"&&(!data.forecast||!Array.isArray(data.history_dates)))throw new Error("The sales analysis response is incomplete.");
    if(path!=="/tablet"&&(!Array.isArray(data.days)||!Array.isArray(data.dishes)))throw new Error("The weekly outlook response is incomplete.");
    if(request!==state.request)return;state.data=data;state.cache.set(key,data);
  } catch(error) {
    if(error.name==="AbortError"||request!==state.request)return;
    state.error=error instanceof TypeError?"Cannot reach the sales API. Start the demo and retry.":error.message;
  } finally {if(request===state.request){state.loading=false;paint();}}
}
document.querySelector("#controls").addEventListener("submit",e=>{e.preventDefault();state.cache.clear();load(true);});
app.addEventListener("click",e=>{
  const b=e.target.closest("button");if(!b)return;
  if(b.dataset.view){state.view=b.dataset.view;load();}
  if(b.dataset.source){state.source=b.dataset.source;load();}
  if(b.dataset.date){dateInput.value=b.dataset.date;state.view="next";state.cache.clear();load();}
  if(b.dataset.approve){state.decisions.set(b.dataset.approve,"approved");paint();panel.querySelector("[data-review]")?.focus();}
  if(b.dataset.reject){state.decisions.set(b.dataset.reject,"rejected");paint();panel.querySelector("[data-review]")?.focus();}
  if(b.dataset.review){state.decisions.delete(b.dataset.review);paint();panel.querySelector("[data-approve]")?.focus();}
  if(b.hasAttribute("data-retry"))load(true);
});
load();
