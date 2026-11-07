// Mock screen payload for the prep tablet.
// Synthetic. Replace this file when the recommendations backend is ready.
// The page reads window.PREP_MOCK.screens and does not call the network.
window.PREP_MOCK = {
  screens: [
      {
        name: "Wednesday lunch",
        clock: "Wed 9:30",
        early: "Dinner brisket starts at 1:00. It takes 4 hours, and dinner starts at 5:00.",
        proposal: {
          hours: "3:00–4:00",
          text: "Repeating. After school. Busy on 3 of the last 4 Wednesdays.",
          approved: "After school approved. It is a rush from now on. Portions for today are on Rest of today.",
          rejected: "Rejected. Nothing to prep for 3:00–4:00.",
          rushTitle: "After school",
          rushReason: "Approved for today. Busy on 3 of the last 4 Wednesdays.",
          listId: "school"
        },
        dishes: { burgers: "Burgers", bolognese: "Bolognese", pad: "Pad thai", fries: "Fries", brisket: "Brisket" },
        lists: {
          lunch: { title: "Lunch", hours: "11:00–2:00", reason: "Standing rush. Next rush.", why: "Last four Wednesdays at lunch, plus about 20% more orders than this date last year.", order: ["burgers", "bolognese", "pad", "fries"], counts: { burgers: 14, bolognese: 8, pad: 9, fries: 6 } },
          dinner: { title: "Dinner", hours: "5:00–7:30", reason: "Standing rush.", why: "Wednesday dinners run heavier than lunch. Brisket has to start at 1:00.", order: ["burgers", "bolognese", "fries", "brisket"], counts: { burgers: 18, bolognese: 10, fries: 11, brisket: 6 } },
          school: { title: "After school", hours: "3:00–4:00", reason: "Approved for today.", why: "Busy on 3 of the last 4 Wednesdays at these hours.", order: ["burgers", "fries"], counts: { burgers: 10, fries: 8 } },
          thuLunch: { title: "Lunch", hours: "11:00–2:00", reason: "Standing rush.", why: "Last four Thursdays at lunch. No extra lift from last year.", order: ["burgers", "bolognese", "pad", "fries"], counts: { burgers: 11, bolognese: 6, pad: 8, fries: 5 } },
          thuDinner: { title: "Dinner", hours: "5:00–7:30", reason: "Standing rush.", why: "Thursday dinner matches the last four Thursdays. Brisket still starts at 1:00.", order: ["burgers", "bolognese", "fries", "brisket"], counts: { burgers: 16, bolognese: 8, fries: 9, brisket: 6 } }
        },
        prep: {
          lunch: {
            now: [
              { name: "Ground beef", amount: "3 lb", uses: "Camera sees 4 lb of 7 lb. Burgers, bolognese." },
              { name: "Shrimp", amount: "9 portions", uses: "Camera sees none. Portion now. Pad thai." },
              { name: "Buns", amount: "14", uses: "Camera sees a full tray. Pull them now. Burgers." }
            ],
            wait: [
              { name: "Pasta", amount: "2 lb", uses: "Cook when lunch starts. Bolognese." },
              { name: "Rice noodles", amount: "9 portions", uses: "Soaks and dies if it waits. Pad thai." },
              { name: "Potatoes", amount: "3 lb", uses: "Fry when lunch starts. Fries." },
              { name: "Eggs", amount: "9", uses: "Pad thai." },
              { name: "Tomato", amount: "14", uses: "Burgers, bolognese." },
              { name: "Onion", amount: "8", uses: "Bolognese." },
              { name: "Lettuce", amount: "14", uses: "Wilts if it is dressed early. Burgers." },
              { name: "Bean sprouts", amount: "9 handfuls", uses: "Pad thai." },
              { name: "Salt", amount: "to taste", uses: "All of these dishes." },
              { name: "Pepper", amount: "to taste", uses: "Burgers, bolognese." },
              { name: "Fish sauce", amount: "9 tbsp", uses: "Pad thai." },
              { name: "Oil", amount: "1 cup", uses: "Fries, pad thai." }
            ]
          },
          dinner: {
            now: [
              { name: "Ground beef", amount: "5 lb", uses: "Camera sees 4 lb of 9 lb. Burgers, bolognese." }
            ],
            wait: [
              { name: "Brisket", amount: "6 portions", uses: "Camera sees none. Start at 1:00, not at 9:30." },
              { name: "Buns", amount: "18", uses: "Pull closer to dinner. Burgers." },
              { name: "Pasta", amount: "2.5 lb", uses: "Cook when dinner starts. Bolognese." },
              { name: "Potatoes", amount: "5 lb", uses: "Fry when dinner starts. Fries." },
              { name: "Salt", amount: "to taste", uses: "All of these dishes." },
              { name: "Pepper", amount: "to taste", uses: "Burgers, bolognese, brisket." },
              { name: "Oil", amount: "2 cups", uses: "Fries." }
            ]
          },
          school: {
            now: [
              { name: "Ground beef", amount: "2.5 lb", uses: "Camera sees none. Burgers." }
            ],
            wait: [
              { name: "Buns", amount: "10", uses: "Burgers." },
              { name: "Potatoes", amount: "4 lb", uses: "Fry when this rush starts. Fries." },
              { name: "Salt", amount: "to taste", uses: "Burgers, fries." },
              { name: "Oil", amount: "1 cup", uses: "Fries." }
            ]
          },
          thuLunch: {
            now: [
              { name: "Ground beef", amount: "5 lb", uses: "Camera sees none. Burgers, bolognese." },
              { name: "Shrimp", amount: "8 portions", uses: "Portion ahead. Pad thai." }
            ],
            wait: [
              { name: "Pasta", amount: "1.5 lb", uses: "Cook when lunch starts. Bolognese." },
              { name: "Rice noodles", amount: "8 portions", uses: "Pad thai." },
              { name: "Potatoes", amount: "2.5 lb", uses: "Fry when lunch starts. Fries." },
              { name: "Salt", amount: "to taste", uses: "All of these dishes." },
              { name: "Fish sauce", amount: "8 tbsp", uses: "Pad thai." }
            ]
          },
          thuDinner: {
            now: [
              { name: "Ground beef", amount: "8 lb", uses: "Camera sees none. Burgers, bolognese." }
            ],
            wait: [
              { name: "Brisket", amount: "6 portions", uses: "Start at 1:00. Brisket." },
              { name: "Buns", amount: "16", uses: "Burgers." },
              { name: "Pasta", amount: "2 lb", uses: "Bolognese." },
              { name: "Potatoes", amount: "4 lb", uses: "Fries." },
              { name: "Salt", amount: "to taste", uses: "All of these dishes." },
              { name: "Pepper", amount: "to taste", uses: "Burgers, bolognese, brisket." }
            ]
          }
        },
        today: ["lunch", "dinner"],
        tomorrow: ["thuLunch", "thuDinner"],
        sums: {
          week: { label: "This week", order: ["burgers", "fries", "pad", "brisket"], counts: { burgers: 86, fries: 40, pad: 28, brisket: 18 } },
          month: { label: "This month", order: ["burgers", "fries", "pad", "brisket"], counts: { burgers: 340, fries: 160, pad: 110, brisket: 70 } },
          next: { label: "Next month", order: ["burgers", "fries", "pad", "brisket"], counts: { burgers: 360, fries: 170, pad: 120, brisket: 74 } }
        },
        setup: {
          hours: ["Lunch 11:00–2:00", "Dinner 5:00–7:30"],
          durations: ["Brisket, 4 hours", "Bolognese, 25 minutes", "Pad thai, 15 minutes", "Burgers, 10 minutes", "Fries, 8 minutes"]
        }
      },
      {
        name: "Quiet Tuesday",
        clock: "Tue 4:30",
        early: "",
        proposal: null,
        dishes: { burgers: "Burgers", salad: "Salad", fries: "Fries" },
        lists: {
          lunch: { title: "Dinner", hours: "5:00–7:30", reason: "Standing rush. Next rush.", why: "Last four Tuesdays at dinner. A quiet night, no lift from last year.", order: ["salad", "burgers", "fries"], counts: { salad: 7, burgers: 4, fries: 3 } },
          dinner: { title: "Dinner", hours: "5:00–7:30", reason: "Standing rush.", why: "Last four Tuesdays at dinner. A quiet night, no lift from last year.", order: ["salad", "burgers", "fries"], counts: { salad: 7, burgers: 4, fries: 3 } },
          wedLunch: { title: "Lunch", hours: "11:00–2:00", reason: "Standing rush.", why: "Last four Wednesdays at lunch.", order: ["burgers", "salad", "fries"], counts: { burgers: 6, salad: 5, fries: 2 } },
          wedDinner: { title: "Dinner", hours: "5:00–7:30", reason: "Standing rush.", why: "Last four Wednesdays at dinner.", order: ["salad", "burgers", "fries"], counts: { salad: 8, burgers: 5, fries: 3 } }
        },
        today: ["dinner"],
        tomorrow: ["wedLunch", "wedDinner"],
        sums: {
          week: { label: "This week", order: ["salad", "burgers", "fries"], counts: { salad: 40, burgers: 28, fries: 16 } },
          month: { label: "This month", order: ["salad", "burgers", "fries"], counts: { salad: 150, burgers: 110, fries: 60 } },
          next: { label: "Next month", order: ["salad", "burgers", "fries"], counts: { salad: 160, burgers: 120, fries: 64 } }
        },
        prep: {
          lunch: {
            now: [
              { name: "Ground beef", amount: "1 lb", uses: "Camera sees none. Burgers." }
            ],
            wait: [
              { name: "Buns", amount: "4", uses: "Pull when dinner starts. Burgers." },
              { name: "Potatoes", amount: "1.5 lb", uses: "Fry when dinner starts. Fries." },
              { name: "Lettuce", amount: "11", uses: "Camera sees a half pan. Salad, burgers." },
              { name: "Tomato", amount: "11", uses: "Salad, burgers." },
              { name: "Salt", amount: "to taste", uses: "All of these dishes." },
              { name: "Oil", amount: "1/2 cup", uses: "Fries, salad." }
            ]
          },
          dinner: {
            now: [
              { name: "Ground beef", amount: "1 lb", uses: "Camera sees none. Burgers." }
            ],
            wait: [
              { name: "Buns", amount: "4", uses: "Burgers." },
              { name: "Potatoes", amount: "1.5 lb", uses: "Fries." },
              { name: "Lettuce", amount: "11", uses: "Salad, burgers." },
              { name: "Tomato", amount: "11", uses: "Salad, burgers." },
              { name: "Salt", amount: "to taste", uses: "All of these dishes." },
              { name: "Oil", amount: "1/2 cup", uses: "Fries, salad." }
            ]
          },
          wedLunch: {
            now: [
              { name: "Ground beef", amount: "1.5 lb", uses: "Camera sees none. Burgers." }
            ],
            wait: [
              { name: "Buns", amount: "6", uses: "Burgers." },
              { name: "Potatoes", amount: "1 lb", uses: "Fries." },
              { name: "Lettuce", amount: "11", uses: "Salad, burgers." },
              { name: "Tomato", amount: "11", uses: "Salad, burgers." },
              { name: "Salt", amount: "to taste", uses: "All of these dishes." }
            ]
          },
          wedDinner: {
            now: [
              { name: "Ground beef", amount: "1.25 lb", uses: "Camera sees none. Burgers." }
            ],
            wait: [
              { name: "Buns", amount: "5", uses: "Burgers." },
              { name: "Potatoes", amount: "1.5 lb", uses: "Fries." },
              { name: "Lettuce", amount: "13", uses: "Salad, burgers." },
              { name: "Tomato", amount: "13", uses: "Salad, burgers." },
              { name: "Salt", amount: "to taste", uses: "All of these dishes." },
              { name: "Oil", amount: "1/2 cup", uses: "Fries, salad." }
            ]
          }
        },
        setup: {
          hours: ["Lunch 11:00–2:00", "Dinner 5:00–7:30"],
          durations: ["Salad, 20 minutes", "Burgers, 10 minutes", "Fries, 8 minutes"]
        }
      }
    ]
};
