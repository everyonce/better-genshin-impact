# Raptor ambush recovery checkpoint

The Raptor rescue is complete, but the subsequent ambush is unfinished. Act II remains locked at AR9, 650/1300. Continue the mission after this engineering checkpoint.

Validated behavior: post-rescue search reached the ambush; translated regional map labels use consistent OCR centers; guarded Kaeya-to-Lumina recovery switch succeeded. Exact level13 edge scanning recovered the left-hand target at14249/14251. Lumina upgrade13->17 was confirmed14230, using8AdventurersExperience (40000 item EXP) and8000 Mora, leaving103604. Equipped stats14233:2764HP,97ATK,238DEF. Do not attribute item EXP to combat.

Combat remains ineffective at range and during Freeze. A camera600 input measured about23degrees; later camera correction centered enemies but incoming damage triggered the existing70percent health floor. No kill or ambush completion is claimed. Two native rotations did not establish damage and were not repeated unchanged. The new opt-in pursuit mode has at most4 camera corrections and4x600ms forward steps, fresh target/health checks,20s overall combat bound, and guaranteed release. Its live combat validation remains pending. Four-press Freeze recovery has regression coverage but no confirmed successful live escape yet.

Free recovery: Windrise teleportb97b9567; exact safe landing corridor and bounded Statue approacha19969e6; first healing partial, then392cb61c confirmedKaeya4015/4015 at14343 and inventorypause14346. No new death/fall, food, resin, premium spending, difficulty change, or application/RDP restart in this window. Quest remains tracked; encounter reset on retreat is possible.

Validation:1728 tests passed,0 failed,43724.6849ms using the isolated candidate in artifacts/raptor-ambush-publication. An initial test caught unintended generic level13 plan acceptance; corrected scope requires explicit Raptor approach/pursuit. The test runner's final console print encountered Windows encoding after the suite completed; the saved log confirms all1728 passed. Targeted team26, Raptor21 and Statue10 also passed. No native build needed.

Runtime adapter is validated HEAD plus exact level13 crop only. Runtime mission is validated HEAD plus the scoped Statue change. Unrelated source drafts remain excluded. No new runtime copy or irreversible cleanup. Retention04:52UTC:9,301,561,344B free;256 recent/504,417,443B plus31 pinned/66,446,604B, within existing limits.

Accounting14227->14347:21 terminal requests,172296ms total request time,4320ms key-hold budget. These overlap capture, wait, menus and loading and are not productive gameplay time. Model-selected movement/menu plans, hotloads and diagnoses are interventions. Ledger and current checkpoint remain authoritative for later activity.
