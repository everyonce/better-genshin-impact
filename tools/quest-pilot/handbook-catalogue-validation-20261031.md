# Bounded enemy catalogue controls, 2026-10-31

The R61 script bridge can open the Adventurer Handbook, select its Easy enemy category, scroll the icon list, inspect one selected enemy and track an explicitly named Mondstadt enemy. These are menu controls; they do not grant a movement route or start combat.

## Commands

Use the existing request envelope with a unique `id`, current `session`, `expectedFrameId` and `createdAt`. The three new commands use `mission: "questStep"`:

| Step | Additional fields | One bounded operation |
| --- | --- | --- |
| `handbookCatalogueScroll` | None | Move to the left catalogue and send eight downward scroll events, 100 ms apart. |
| `handbookCatalogueSelect` | Integer `x`, `y` | Click one icon strictly inside `420 < x < 940`, `265 < y < 870` in the 1920×1080 layout. |
| `handbookCatalogueTrack` | Exact English `enemyName` | Click Navigate only when the selected title matches and its location ends in Mondstadt. |

All three require a fresh, same-session Easy catalogue with the expected Handbook anchors and no category popup. Tracking checks the selected title, location and Navigate button together. Location comma spacing is normalized because live OCR returned `OStormbearer Mountains,Mondstadt`; the leading `O` is preserved, and enemy names are not fuzzy-matched. Extra request fields are rejected.

`VK_F1` opens the Handbook only from a fresh healthy ground scene. The existing `actTwoHandbookEnemies`, new `actTwoHandbookEasyCategory` and `actTwoHandbookEasySelect` steps reach the Easy catalogue. Recognized Handbook and map screens can be closed with Escape. The category header accepts the observed `AlL` casing.

Keep the Handbook open between scrolling, selecting and tracking: reopening it resets the filter to All. A stopped script releases its task ownership even when the menu is deliberately retained.

## Evidence and limits

Each catalogue command pins its pre-input JSON/PNG, records the script revision and physical-call sequence, and checks STOP, focus, session and freshness before dispatch. A button-down attempt receives one cleanup button-up attempt even on failure. These legacy UI receipts use `Date.now` limits of 1,000 ms since OCR completion and 2,000 ms since capture began. They are separate from AgentStream's native QPC/150 ms feedback contract and remain diagnostic evidence, not training-qualified gameplay.

Live evidence is retained under `artifacts/live/2026-10-30-endurance/`:

- `camp-handbook-pilot-05` and `-06`: Easy catalogue scrolling, menu retained, original owner idle and RDP minimized after each visit.
- `camp-handbook-pilot-07`: one icon selection confirmed Slime in Stormbearer Mountains, Mondstadt.
- `camp-handbook-pilot-08`: tracking refused before keyboard/mouse dispatch because of OCR comma spacing; the failed receipt is preserved.
- `camp-handbook-pilot-09`: the corrected parser admitted one Navigate click, followed by Escape and a verified world return at 2220/2764 HP. The returned minimap showed the Slime tracking marker. The map screenshot caught a transition, so it is not a settled destination-coordinate proof.

All visits used the original R56 host, R61 child and existing Genshin process in minimized RDP. Temporary script groups and owned requests were removed. Script overlays and raw owner status are retained in the `handbook-*-install-v1` folders; no native binary was replaced for these menu changes.

Validation: 78 focused JavaScript tests passed, including actual run08 OCR and adapter dispatch regressions. Independent review found no actionable issues and confirmed run08 had zero keyboard/mouse action events. The required solution restore/build passed before subsequent native-profile work. Tracking is verified; enemy arrival, attacks, damage and a defeated enemy are not established by these menu trials.
