// Screen payload for the prep tablet.
// Every count, reason, and ingredient is a placeholder.
// Replace this module when the recommendations backend and filled data are ready.
// The sales API at /orders does not provide this shape.

const dish = (id) => ({ id, name: "Dish", prep: "—" });

const rush = (title, hours, reason) => ({
  title,
  hours,
  reason,
  why: "Reason arrives with the recommendations.",
  dishes: [dish("a"), dish("b"), dish("c")],
});

const ingredient = (when) => ({
  name: "Ingredient",
  amount: "—",
  note:
    when === "now"
      ? "On hand arrives from the walk-in camera."
      : "Waits until this rush.",
});

const prep = {
  now: [ingredient("now"), ingredient("now")],
  wait: [ingredient("wait"), ingredient("wait"), ingredient("wait")],
};

export const screen = {
  clock: "—:—",
  early: "Early prep appears here when a later rush must start before it is next.",
  proposal: {
    hours: "—:— – —:—",
    text: "A newly found rush appears here until the lead approves it.",
    approved: "Approved. Its prep counts show on Rest of today.",
    rejected: "Rejected. Nothing to prep.",
    rushId: "proposed",
  },
  rushes: {
    next: rush("Next rush", "—:— – —:—", "Standing rush. Next rush."),
    later: rush("Later rush", "—:— – —:—", "Standing rush."),
    tomorrowEarly: rush("Next rush", "—:— – —:—", "Standing rush."),
    tomorrowLate: rush("Later rush", "—:— – —:—", "Standing rush."),
    proposed: rush("Proposed rush", "—:— – —:—", "Approved for today."),
  },
  prep: {
    next: prep,
    later: prep,
    tomorrowEarly: prep,
    tomorrowLate: prep,
    proposed: prep,
  },
  today: ["next", "later"],
  tomorrow: ["tomorrowEarly", "tomorrowLate"],
  ahead: {
    week: { label: "This week", dishes: [dish("a"), dish("b")] },
    month: { label: "This month", dishes: [dish("a"), dish("b")] },
    next: { label: "Next month", dishes: [dish("a"), dish("b")] },
  },
  setup: {
    hours: ["Lunch —:— – —:—", "Dinner —:— – —:—"],
    durations: ["Dish, —"],
  },
};
