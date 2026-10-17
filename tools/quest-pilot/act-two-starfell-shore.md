# Bounded Starfell shore crossing

This is a separate state-specific replacement for the retired generic southwest ground-navigation exit from the Starfell Statue. The generic route remains retired. The coastal cliff approach also remains retired. Published `7bd208bb` covers teleport/map recovery and coastal camera observation only, not this swimming routine.

`actTwoStarfellShore` starts only from the grounded Statue spawn. It follows a fixed, small lake corridor with no sprint, jump, combat or interaction. Each600ms forward input requires fresh account, session, position, full4015HP, no enemies, and either ground controls or a positively recognized swim control. Movement is capped at7.2seconds; stalls, increased destination distance and changed controls stop it. The final version requires a same-frame yellow stamina arc of at least25pixels height during every swimming cycle. All image resources are released, including on errors.

`actTwoStarfellShoreContinue` starts only within2units of the first measured endpoint(-1319.3574,2552.5801), requires a stamina arc at least40pixels tall, and caps forward input at6seconds. Both requests finish with verified Inventory pause. A scoped map escape exists for positively recognized water in the same lake corridor.

Live validation in session `mvcuzen8-drrh7eb3gqe`:

- `b94ad8bda9f349f68382a36b848974a4`:12forward inputs,7200ms commanded input,34667ms request. Shore distance27.694→14.234units; swimming recognized292–300. This first live version preceded the stamina guard extension to the initial leg.
- `93bf0a4fbd9443d4b864d9f1c9fb19ad`:8forward inputs,4800ms commanded input,22718ms request. Stamina arc53pixels at306→33at313→31at314. Ground controls returned314 in shallow water; this was not yet dry-shore arrival.
- `069e80cf2fe347a0a7a3335e56f0d2c6`:3guarded ground inputs,1800ms commanded input,14969ms request. Frame323 visually confirms dry bank at(-1308.1836,2542.1289). HP4015throughout. No food, resin, currency, death or fall.
- `186480003d2740289b31cb2ccc572ed1`:subsequent western-bank route reached bothpoints with13movement pulses/8278ms,37255ms request, no climb recovery. This validates usable ground continuation, not waypoint activation.

The swimming requests consumed12seconds of forward input in57.385seconds of request time; final shore footing verification added14.969seconds. Request time includes observations and pause transitions; this is not a whole-mission efficiency benchmark. The final first-leg stamina gate and widened water-map escape are tested but not separately live exercised. Continuation recognition, stamina monitoring, ground transition and key release were exercised successfully.
