# Act II prerequisite: Windwail road approach

Act II remains locked at Adventure Rank 9, 120/1300. Cyrus's Not to be Missed is complete; its turn-in awarded 100 Adventure EXP. The next selected goal is the freshly inspected Blossom of Revelation in Windwail Highland: 20 Original Resin for 100 Adventure EXP and character experience materials. No blossom has been activated or claimed, and resin spending remains zero.

The old blind fog-road/cliff attempt remains retired. This attempt uses the bundled static map to identify the continuous northern Windrise road, then checks real terrain after each bounded segment. Static map geometry is a route hypothesis, not proof of walkability.

Live observations:

- Four native segments used 8.095, 12.054, 10.116 and 6.579 seconds respectively. Their plausible minimap displacement estimates were 45.39, 79.50, 61.78 and 21.79 metres; these are estimates, not independent distance measurements.
- The fourth segment reached a low rock and stopped climbing. Three existing 600ms climb holds reached its visible top without damage. Do not replay the grass shortcut without this terrain check.
- Global minimap matching then produced implausible coordinates. Entry guards rejected movement. A reviewed 2.4-second visual step and existing local-anchor navigation recovered travel.
- The main road junction near (-1021,2041) contained mixed-level hilichurls. Existing visual-location combat used 3 skills/18 attacks, then 1 skill/3 attacks. Exact-level14 recognition recovered the final depleted health bar; another 1 skill/3 attacks defeated the shield enemy. Dropped Damaged Mask was visible; pickup was not confirmed.
- A subsequent Electro Slime encounter used 2 skills/6 attacks. The reward display showed Character EXP x11 and Mora x27; these are not Adventure EXP. Kaeya returned to 2635/2635 HP through his existing equipment passive, without food use.

All decisions and reviewed route/visual plans are model interventions. No native build, application/script/RDP restart, death, premium spend or resin spend occurred during these road segments. Menus were independently verified as Inventory pauses after each terminal request. Durations and actions remain in the durable event ledger.

Pending source improvements: the post-Cyrus map icon profile and regional panel OCR tolerance passed focused tests and live inspection. The upgraded Kaeya full-health native-route guard passed live travel. A local-anchor candidate filter for native-route observation rejects the recorded distant coordinate jump; this last change is tested offline but still awaits live validation and publication.

At the fog boundary, fresh full-map observation confirmed the character on the westbound road, with the Blossom southwest of it. The existing regional-map visual handler already supports eight guarded 800ms inputs and stops on threats, climbing or low health. Adding the observed three-label map-scale profile passed 34 focused tests and live request `mission-5a1110d77cbc4570a17c3c76ec76f36a`: eight steps, full HP, independently verified Inventory pause. This is reviewed visual travel; minimap coordinates are explicitly unverified.

Complete working-tree regression: 1,528 tests passed, zero failures, 35.043 seconds. No native source changed or native rebuild was needed. Storage audit at 05:25 UTC: 232 recent images / 534,411,247 bytes and 31 evidence images / 65,773,254 bytes; 7,175,589,888 bytes free. Existing retention remained active; no new irreversible cleanup was performed.
