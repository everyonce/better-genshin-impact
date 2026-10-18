# Target switch review, 2026-10-18

Act II is still locked at AR9, 955/1300. No Adventure EXP or resin reward was verified from the shield, waypoint59, or Cyrus chest work below. These are costs, not quest milestones.

## Cyrus chest lead: bounded search closed without locating the chest

The lead was an Oct15 screenshot from a different session near (-1119.105,2289.428), showing a chest about6m away while the character was taking damage. The Cyrus quest itself had already completed. This old image did not establish a currently unopened chest.

On Oct18 the controller followed the grass approach, reached the old vantage at (-1117.785,2288.001), and found a boulder occluding the view (7069). One wider clearing pass reached (-1139.625,2298.451), followed by a camera inspection (7104). The visible NPC was Vile, not a chest. The current observations had no chest, interaction prompt, or enemies. The pass did not locate the chest and cannot prove it was looted. Searching more of the area had no fresh landmark, supported chest location or bounded route to test, so this stale lead was retired after that clearing pass. Reopen only with a current positive chest witness or another materially new location.

Receipts:30ad8db10ff34b268a7d2f19ec4bb697 (gate), d7ef9c9b7f644e98bb806a2bf3d49257 (grass), f1f6d2f4f6ec4dfd820a026f1d37fa15 (continuation),55a71d58884c4c49ab1e4bcdc70648d3 (old vantage),60720099e143494993bcf4da0d72ee0a (clearing),5644bec86c7843558eb541d2855eb4bc (camera). The useful result is an evidence-based rejection of the old location; it is not objective progress.

## Decoy experiment

Safe Windrise practice c0802774b57b4486a08c23fbed5d6a0f pressed E once, returned to Kaeya and verified Inventory. Before-E260071200 has the ready skill icon; after-E260071201 has14.4s cooldown. Those UI facts alone are insufficient to prove deployment. Frame7123 and the preserved deployment crop independently show Baron Bunny's red head/ears and foot partly behind Kaeya. That supports a deployed decoy, with placement occluded. It does not establish taunt, explosion, shield application, removal or a defeat.

Native read-only replay b846887d0c474f0a9a172a47ca9eb852 tested ready/cooldown/Kaeya frames: ready true/false/false at271/353/580ms, no inputs. Field support requires one-use reviewed encounter/facing, fresh positive ready E, >=95% health, bounded exposure, key release, return to Kaeya and verified pause. The emergency map/Statue retreat is already live-validated. Only one field cast is authorized by this experiment before reviewing actual placement and response. No repeated E loop or lowered confidence threshold.

## Accounting limitations

Receipt-bounded reports are generated from the durable event ledger. Request time overlaps observation/input time. Verified Inventory gaps are a lower bound and exclude within-request pauses. Productive gameplay, model decision time and unclassified time must not be invented from the remainder. Candidate travel/preparation without a verified reward is reported explicitly as switching/search overhead; there is no measured objective-efficiency gain in this window.

## Experiment closure and navigation regression

One field E cast6d75689ee2034cb79802bffd39f046f0 returned Kaeya; Amber1733unchanged, Kaeya4015->3845before switch. The following stationary aftermath request08f58878165240e08a35a632afc626af accepted a target inside arrival tolerance, performed zero movement and lost171HP, ending3674. This was unsafe exposed observation, not retreat or productive play. Counter remained4/9; no useful taunt, burning, shield removal or defeat established. Field deployment is occluded/unknown; the safe practice deployment remains confirmed. Emergency map and Windrise teleport succeeded, Statue healed to4015 without food/resin. Experiment closed; do not repeat without a ready bounded reposition and sufficient guarded effect observation.

The preserved before/after regression rejects hazard-side no-op navigation before unpause. An escape plan must place its endpoint beyond arrival tolerance, require movement>=4mapunits and distance gain>=6from a reviewed hazard location, and verify both after actual movement. This proves geographic separation from that location, not clearance from a moving enemy. Missing/unresolved coordinates, stale witnesses, one-use mismatch and zero movement cannot establish escape. Recorded guard tests pass; no live escape with this new guard has run.

Measured Cyrus window:644742ms wall,151379ms requests,103511ms consecutive world sample spans,443338ms verified Inventory gaps,50025ms unclassified. Decoy practice through healing:1251294ms wall,206525ms requests,62009ms consecutive world sample spans,816384ms verified Inventory gaps,228385ms unclassified. These overlapping exposure/request measures do not establish useful objective play time. Verified reward-bearing progress in both windows:0EXP,0defeats,0resin. Switching, inspection and preparation consumed these windows; no efficiency gain claimed.

## Current supported target assessment

Journal7252 confirms Outrider Style still requires entering Raptor's Hideout; no new completion/reward. Prior failed domain approaches remain retired. Current map7266 explicitly shows an unopened Windwail Highland Statue requiring activation (native tp.json id3 at x=-575.6,y=1859.34). Springvale teleport8a8cd816 reached fullHP but unconstrained GPS returned impossible8759coordinates; local navigation095a70af refused before movement. Full map7292 independently shows the current waypoint and unopened Statue southwest. Use reviewed regional ground actions, fresh terrain/compass observations and bounded stop conditions. Do not infer position from the failed GPS or replay retired cliffs. Camera-only ffc0d3a7 reacquired visible distant red Statue beacon; no movement/reward yet at that checkpoint.
