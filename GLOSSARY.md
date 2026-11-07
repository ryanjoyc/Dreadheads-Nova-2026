# Rush prep

How a kitchen decides how many portions of each dish to make ahead of busy service.

## Language

**Dish**:
A menu item the kitchen makes as one countable portion. Variants and modifiers share that dish's row, so a burger, a cheeseburger, and a burger with no onion are one dish.
_Avoid_: Ingredient, modifier, special request

**Order**:
A guest's purchase on DoorDash or Grubhub.
_Avoid_: Ticket, counter sale

**Context day**:
A date marked as a holiday, a game, or weather, and left out of the ordinary average.
_Avoid_: Ordinary weekday, rush

**Prep**:
The portion count to have ready for a rush: the average ordered during that rush's hours on the last eight same weekdays, in fifteen-minute slots, excluding context days, optionally moved to between half and double for a holiday, a game, or weather, with a reason. It does not fall as the kitchen cooks.
_Avoid_: Fire time, purchase, inventory count, last year, ingredient weight

**Prep duration**:
How long a dish takes to prep. The restaurant sets it. It is not part of an order, and it is not inferred from orders. Early prep happens when this duration is longer than the time left before a later rush. A longer duration is a harder dish.
_Avoid_: Cook time guessed from orders, fire time

**Early prep**:
Prep for a later rush that must start before that rush is the next one. The kitchen is told about it while that later rush is still not next. It is not added to the current rush's dish count.
_Avoid_: Blended count

**Rush**:
A stretch of service when guests order enough that the kitchen has to prep ahead.
_Avoid_: Peak, one-time spike

**Standing rush**:
Lunch or dinner. The restaurant sets its hours. Those hours are not inferred from orders.
_Avoid_: Repeating rush

**Repeating rush**:
A busy stretch outside standing rushes that the lead has approved, after those same hours were busy on at least three of the last four same weekdays.
_Avoid_: Standing rush, one-time spike, rush proposal

**One-time spike**:
A busy stretch that has not repeated. It is not a rush. It gets a prep list only when the lead approves it for that occurrence.
_Avoid_: Rush, promotion treated as fact

**Rush proposal**:
A newly found stretch the lead has not approved. It has hours, a repeating or one-time call, and a reason. It has no prep list.
_Avoid_: Standing rush, repeating rush

**List order**:
The sequence of dishes on one prep list. It starts with the largest prep count first. The kitchen can reorder that list, and everyone sees that sequence. Another rush keeps its own order. Reordering does not change a count.
_Avoid_: Priority switch, personal sort

**Service window**:
Next rush, the rest of today, or tomorrow. These are the tablet's main views.
_Avoid_: Week, month

**Further ahead**:
The sum of the rush guidelines inside a week, a month, or the next month. It is portions expected across those rushes, not one pile to cook now.
_Avoid_: Service window

**Prep list**:
The list of prep counts for one window. Every staff member sees the same counts. Nobody edits a count or checks one off.
_Avoid_: Ticket, schedule, fire board
