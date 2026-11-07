import { test, expect } from "@playwright/test";
import { writeFileSync, readFileSync, mkdirSync } from "node:fs";

async function loaded(page, day = "2026-10-29", source="all") {
  await expect(page.getByRole("status")).toContainText(`${day} · ${source}`);
  await expect(page.locator("#panel")).toHaveAttribute("aria-busy", "false");
}
async function settings(page) {
  const summary=page.getByText("Demo settings",{exact:true});
  if(!(await summary.locator('..').getAttribute('open') !== null)) await summary.click();
}

test("real sales fill Kurt's rush-first tablet and time horizons", async ({page}) => {
  await page.goto("/"); await loaded(page);
  await expect(page.getByRole("region", {name:"Lunch rush",exact:true})).toContainText("Tangy Fried Chicken Rice Bowl");
  await expect(page.getByRole("heading", {name:"Lunch rush · 12:15–12:45",exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Load day",exact:true})).not.toBeVisible();
  await expect(page.locator("svg")).toHaveCount(0);
  await page.getByRole("button", {name:"Rest of today",exact:true}).click(); await loaded(page);
  await expect(page.getByRole("region")).toHaveCount(3);
  await page.getByRole("button", {name:"Tomorrow",exact:true}).click(); await loaded(page,"2026-10-30");
  await expect(page.getByRole("heading", {name:/Whole day/})).toBeVisible();
  await page.getByRole("button", {name:"Further ahead",exact:true}).click(); await loaded(page);
  await expect(page.getByRole("heading",{name:"Next seven days",exact:true})).toBeVisible();
  await page.getByRole("button", {name:"Setup",exact:true}).click(); await loaded(page);
  await expect(page.getByText(/Forecast: 755 orders. Observed on this date: 778 orders./)).toBeVisible();
  await expect(page.getByText(/2026-10-01, 2026-10-08, 2026-10-15, 2026-10-22/)).toBeVisible();
  await settings(page);
  await page.getByRole("button",{name:"Quiet Sunday",exact:true}).click(); await loaded(page,"2026-10-25");
  await page.getByRole("button",{name:"DoorDash",exact:true}).click(); await loaded(page,"2026-10-25","doordash");
  await expect(page.getByRole("button",{name:"DoorDash",exact:true})).toHaveAttribute("aria-pressed","true");
  await page.getByRole("button",{name:"Grubhub",exact:true}).click(); await loaded(page,"2026-10-25","grubhub");
});

test("empty history and backend failure do not show stale dishes", async ({page}) => {
  await page.goto("/"); await loaded(page); await settings(page);
  await page.getByLabel("Demo date").fill("2026-10-01");
  await page.getByRole("button", {name:"Load day",exact:true}).click(); await loaded(page,"2026-10-01");
  await expect(page.getByRole("heading", {name:"No earlier matching weekdays"})).toBeVisible();
  await page.route("**/api/tablet?**", route=>route.fulfill({status:503,contentType:"application/json",body:'{"detail":"unavailable"}'}));
  await page.getByRole("button", {name:"Busy Thursday",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("Forecast unavailable");
  await expect(page.getByRole("region",{name:"Lunch rush",exact:true})).toHaveCount(0);
  await page.unroute("**/api/tablet?**");
  await page.getByRole("button", {name:"Try again",exact:true}).click(); await loaded(page);
  await expect(page.getByRole("region",{name:"Lunch rush",exact:true})).toBeVisible();
});

test("tablet fits narrow screens and captures the connected demo", async ({page}) => {
  await page.goto("/"); await loaded(page);
  for(const width of [280,320,414,768]){
    await page.setViewportSize({width,height:1000});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  }
  await page.setViewportSize({width:1100,height:1050});
  mkdirSync("../output",{recursive:true});
  await page.screenshot({path:"../output/kstation-demo.png",fullPage:false});
  const html=await page.content();const styles=readFileSync("src/styles.css","utf8");
  writeFileSync("../output/tablet-render.html",html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g,"").replace(/<style\b[^>]*>[\s\S]*?<\/style>/g,"").replace("</head>",`<style>${styles}</style></head>`));
});

test("outside-hours proposal needs approval and rejection keeps it out", async ({page}) => {
  await page.goto("/"); await loaded(page);
  const proposal=page.getByRole("region",{name:"Rush proposal",exact:true});
  await expect(proposal).toContainText("14:30–14:45 proposal");
  await expect(proposal.locator(".row")).toHaveCount(0);
  await page.screenshot({path:"../output/kstation-rush-proposal.png",fullPage:false});
  await page.getByRole("button",{name:"Rest of today",exact:true}).click(); await loaded(page);
  const afternoon=page.getByRole("region",{name:"Afternoon rush",exact:true});
  await expect(afternoon).toHaveCount(0);
  await page.getByRole("button",{name:"Approve for today",exact:true}).click();
  await expect(afternoon).toContainText("14:30–14:45");
  await expect(afternoon).toContainText("Approved for today");
  await expect(afternoon.locator(".row:visible")).toHaveCount(5);
  await afternoon.screenshot({path:"../output/kstation-rush-approved.png"});
  await page.getByRole("button",{name:"Review again",exact:true}).click();
  await expect(afternoon).toHaveCount(0);
  await page.getByRole("button",{name:"Reject rush",exact:true}).click();
  await expect(page.getByRole("region",{name:"Rush decision",exact:true})).toContainText("rejected for today");
  await expect(afternoon).toHaveCount(0);
  await page.reload(); await loaded(page);
  await expect(page.getByRole("button",{name:"Approve for today",exact:true})).toBeVisible();
});

test("optional AI inputs reach the API and analysis evidence stays in Setup", async ({page}) => {
  await page.goto("/"); await loaded(page); await settings(page);
  await expect(page.getByLabel("Use AI analysis (backend key required)")).not.toBeChecked();
  await page.route("**/api/tablet?**", async route=>{
    const url=new URL(route.request().url());
    expect(url.searchParams.get("use_agent")).toBe("true");
    expect(url.searchParams.get("context")).toBe("Campus event");
    // Read the actual baseline, then simulate only the UI-facing model metadata.
    const res=await page.request.get("/api/tablet?date=2026-10-29&use_agent=false");
    const data=await res.json();
    data.analysis={method:"agent",model:"scripted/test",summary:"Scripted UI verification",flags:[],agent_trace:[{tool:"get_rush_forecast",args:{},result:"Four earlier Thursdays"}]};
    await route.fulfill({status:200,contentType:"application/json",body:JSON.stringify(data)});
  });
  await page.getByLabel("Day context").fill("Campus event");
  await page.getByLabel("Use AI analysis (backend key required)").check();
  await page.getByRole("button",{name:"Load day",exact:true}).click(); await loaded(page);
  await page.getByRole("button",{name:"Setup",exact:true}).click(); await loaded(page);
  await expect(page.getByText("AI-assisted · scripted/test",{exact:true})).toBeVisible();
  await page.getByText("How the agent checked the data",{exact:true}).click();
  await expect(page.getByText("get_rush_forecast: Four earlier Thursdays",{exact:true})).toBeVisible();
});
