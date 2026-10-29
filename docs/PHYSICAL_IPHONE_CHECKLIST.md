# Physical iPhone checklist — October 29 features

For the device pass in NEXT_ACTIONS (owner: Georgio). Simulator UI tests cover
each flow; this checks what a simulator cannot: real keyboard, Keychain,
network to the Mac, VoiceOver and Dynamic Type on hardware. Record the iPhone
model, iOS version, backend commit and a screenshot per step in a dated report,
as in [PHYSICAL_IPHONE_TESTING_2026-10-27.md](PHYSICAL_IPHONE_TESTING_2026-10-27.md).

Setup: backend on the Mac bound to its private LAN address, synthetic data from
`scripts/seed_demo.py --timezone <phone timezone>`, the phone on the same
trusted network, Settings → backend URL and development token → Save.

| # | Flow | Expected |
| --- | --- | --- |
| 1 | Today after seeding | Total, "of 2,000 mL · your own goal" progress, 7-day card |
| 2 | Log 250 mL water | Total rises by 250; row appears in History |
| 3 | History → swipe a row → Edit to 300 mL | Total updates; entry shows the new amount |
| 4 | History → swipe → Delete → confirm | Row and its volume disappear from History and Today |
| 5 | Settings → goal 1500 → Done → Save goal | "Goal saved"; Today shows "of 1,500 mL" |
| 6 | Ask Hydra → "Does coffee count toward my fluids?" | Reviewed answer with a tappable Killer et al., 2014 link, shown above the suggestions |
| 7 | Ask Hydra → type "I fainted after my run" → Ask | "Seek care" answer first, in red |
| 8 | Ask Hydra → toggle "Include today's logged total" → any suggestion | "Your log today" shows today's total |
| 9 | Workout forecast → Run synthetic demonstration → Muse Wonder section → Show | Without a recording: "No recorded Muse Wonder result is available yet." |
| 10 | Settings → Export my data (JSON) | Files sheet saves `hydra-export.json` |
| 11 | Settings → Delete all my data → confirm | Message with the count; Today total 0 |
| 12 | Repeat 1, 6 and 11 with VoiceOver on and the largest Dynamic Type size | Everything is read aloud; no text is cut off |

Note anything that differs, with a screenshot. None of these steps calls Meta.
