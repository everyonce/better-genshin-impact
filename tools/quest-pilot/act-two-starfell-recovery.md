# Starfell and coastal waypoint recovery

Act II remains locked at AR9, 955/1300 EXP. No EXP reward or resin expenditure resulted from this route attempt.

The existing guarded teleport adapter now accepts two fixed destinations from `tp.json`: Starfell Lake Statue (id7) and the unlocked coastal waypoint (id6). Account, map, freshness, arrival-distance and verified Inventory pause checks remain in place.

The attempted southwest exit from the Statue entered water. Frame140 in session `mvcuzen8-drrh7eb3gqe` shows swimming, full Kaeya health, and absent ground controls. A narrow recovery permits opening the map at that recorded position only, with fresh identity, full health, no enemies and no objective/UI state. It does not permit swimming movement or combat.

The coastal navigation boundary adds only x[-1660,-1600), y[2600,2700]. Camera-only field observation in that corridor requires full health, no enemies or objective. Ordinary field movement remains rejected outside its previous region.

Live evidence: Starfell arrival112, water map recovery146, coastal arrival149, bounded coastal navigation154–186, lateral rock bypass223, incidental climb safely released242, camera-only recovery255–256. All ended with full4015 health and verified Inventory pause. The direct southwest rock leg and southern wall leg are retired; neither establishes a usable route to Stormbearer Mountains. The target remains waypoint id59; no activation is claimed.

Validation: 1,920 tracked-suite and new regression tests passed, zero failures, 45.623 seconds. An earlier broad glob included unrelated unpublished prototype tests (11 failures); those prototypes were not deployed or included in this change. The new recorded-frame tests reject stale/session/position/health/threat/climb/UI changes and preserve action limits. No native rebuild or app/RDP restart was needed.
