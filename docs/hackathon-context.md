# NOVA 2026 hackathon context

Team reference based on official sources collected November 7, 2026. Discord clarifications below were checked through 11:44 AM Eastern that day. Check [announcements][announcements] for later updates.

## Official sources

- [Event website and schedule][website]
- [Full Hacker Guide: rules, code of conduct, schedule, and prizes][guide]
- [Hacker Tech Guide: OpenRouter, streaming, multimodal inputs, MCP, and React][tech-guide]
- [Opening ceremony slides][opening-slides]
- [Discord resources][resources] and [help/FAQ][help]

Discord links require access to the NOVA server. This document works without the separate local source archive.

## Rules and AI usage

- Teams may have **1–4 members**. The team check-in form determines the final team; contact organizers at check-in for changes.
- Disclose any code reused from prior projects during judging. Libraries are allowed.
- Follow the code of conduct in the [Hacker Guide][guide], including respectful participation and consent around photography.
- NOVA-provided OpenRouter credits are for **AI functionality in the project**. Do not use those keys to power coding agents.
- Keep keys in environment variables and out of Git. Organizers say leaked keys will be disabled, including keys found in private repositories.
- AI-assisted coding is permitted: organizers specifically linked [CMU ChatGPT Edu][chatgpt-edu] for software development. The key restriction above still applies.
- The technical guide provides examples and suggested tools; it does not require a particular stack.

Sources: [Hacker Guide][guide], [November 6 team logistics][team-logistics], [key-use rules][logistics], and [November 7 AI-coding announcement][ai-coding].

## Schedule

Saturday, **November 7, 2026**, at the Swartz Center for Entrepreneurship in Tepper, CMU. All times are Eastern.

| Time | Event |
| --- | --- |
| 10:00–10:30 AM | Check-in and team formation |
| 10:30–11:00 AM | Opening ceremony |
| 11:00 AM | Hacking begins |
| 12:00–1:00 PM | Lunch |
| **5:00 PM** | **Hacking ends** |
| 5:15–6:00 PM | Dinner |
| 6:00–7:45 PM | Judging presentations |
| 7:45–8:30 PM | People's Choice |
| 8:30–9:00 PM | Awards and closing ceremony |

The [website][website] and [guide][guide] agree on this schedule. Opening slides list dinner at 5:00 PM instead of 5:15 PM; confirm that detail with organizers.

## Submission and presentation

- Submit a **GitHub repository link**. A slide deck and demo video are optional under the event-wide instructions.
- Prepare a **five-minute live presentation**, followed by **1–2 minutes of judge questions**. Teams receive an assigned room and judging panel; time limits are strict.
- Indicate sponsor-track participation in the submission.
- Complete [team check-in][check-in] once per team. This is a check-in form, not an identified project-submission form.

Sources: [opening slides, page 6][opening-slides], and [organizer judging/submission announcement][logistics]. Sponsor-specific presentation guidance follows below.

## Event-wide prizes

| Award | Focus | Published reward |
| --- | --- | --- |
| Grand Prize | Overall best project | $2,000 cash |
| Most InNOVAtive | Innovative ideas | Four powerbanks |
| Beyond Limits | Unique methods | Four AirTags |
| Looks Good, Works Good | User design | Four hard disks |
| Community Favorite | People's Choice vote | Four headphones |

Sources: [Hacker Guide][guide] and [opening slides, pages 21–22][opening-slides]. These descriptions are not a numerical judging rubric.

## DoorDash sponsor track

The challenge covers **Front House** restaurant execution and **Back House** business operations. Suggested problems include order preparation timing, packing and pickup, inventory forecasting, bookkeeping, and staffing. Teams may address one or several problems, span both areas, or propose another relevant pain point.

### Demo and technical guidance

- Show a demo with a successful flow and a failure flow. A live demo is preferred; a recording is allowed. Mocks and prototypes may supplement the implementation.
- A slide deck is highly recommended for this sponsor. Explain the problem and solution; useful supporting topics include users, trade-offs, benefits, and technical considerations.
- Sponsor representatives said integration with existing systems is not necessary and confirmed that a tablet interface is a reasonable assumption for restaurant staff.
- Sponsors expressed interest in agentic workflows, computer vision, ML, and other creative AI/software applications.
- For teams with less technical experience, Xun said well-explained processes are useful outputs, especially when the team explains expected AI behavior and limitations. Technical implementation is still encouraged.

These are DoorDash-specific directions and clarifications. Sources: [sponsor slides posted November 7 at 10:54 AM][doordash-slides] and [DoorDash channel replies, November 7, 11:04–11:44 AM][doordash].

### Sponsor prizes

| Award | First place | Second place |
| --- | --- | --- |
| Best Merchant Experience | $500 per team | $250 per team |
| Most Creative Solution | $500 per team | $250 per team |

**DoorDash prizes are DoorDash credits.** Source: [DoorDash prize slide, page 8][doordash-slides], also included on [opening-slides page 18][opening-slides].

## Details to confirm with organizers

The reviewed sources did not establish:

- The project-submission form URL or a submission deadline separate from the 5 PM hacking cutoff.
- Required GitHub repository visibility or a scored judging rubric.
- Detailed Sandia challenge or judging criteria. The guide lists a Sandia track and refers participants to its November 6 talk.

Use [announcements][announcements], [help/FAQ][help], or the relevant sponsor channel for updates. Accenture and Salesforce are listed as workshop hosts/sponsors; the reviewed sources do not establish separate prize-track requirements for them.

[website]: https://nova.scottylabs.org/
[guide]: https://docs.google.com/document/d/e/2PACX-1vRP3wXpj9wwxF-Vsh35jrj6-UolS0sS7PabDWVRSJ3oIP8CfLE08v4-xjZtFL59C2wYBf9sKbSbSiSb/pub
[tech-guide]: https://docs.google.com/document/d/e/2PACX-1vQ23oBFZ0mWiZ0exAmSPhdybzYUwyTXEW48iOTUnAyoLNMuEZD7s0safFPGlKPXsoWA7ucAhpb_zddV/pub
[opening-slides]: https://drive.google.com/file/d/1BSS2uUTL--cLEZIIbN3ivZBG9FjgkzOx/view
[announcements]: https://discord.com/channels/1553503212131057716/1563652315049889863
[resources]: https://discord.com/channels/1553503212131057716/1563652612186701874
[help]: https://discord.com/channels/1553503212131057716/1563659768713838734
[logistics]: https://discord.com/channels/1553503212131057716/1563652315049889863/1568458881775050903
[team-logistics]: https://discord.com/channels/1553503212131057716/1563652315049889863/1568458867732512921
[ai-coding]: https://discord.com/channels/1553503212131057716/1563652315049889863/1568661783164489839
[chatgpt-edu]: https://www.cmu.edu/computing/services/ai/tools/chatgpt/index.html
[check-in]: https://forms.gle/JbbjCgK1PUb7FiCX7
[doordash]: https://discord.com/channels/1553503212131057716/1563655791209095260
[doordash-slides]: https://discord.com/channels/1553503212131057716/1563655791209095260/1568654772452593684
