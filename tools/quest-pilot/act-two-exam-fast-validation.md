# Exam fast observation and reacquisition

The exam lost height while full-frame OCR and PNG writes ran between short flight commands. The course now verifies the account, exact objective, timer, health, and flight controls through small fresh crops before input. Optional reviewed camera turns use this fast entry too. The last raw sample is saved only after immediate inventory pause; replaced samples are disposed.

Near a measured target, one short geometrically consistent distance-occlusion sample is tolerated. A missing marker releases forward immediately and allows at most two local reacquisition polls. Entry menu fade also gets at most two no-input polls. Every sequence remains bounded by eight seconds and twelve samples; lost controls, health or session stop input. A passage candidate is not quest completion.

Live evidence, session `mv9t341i-eft9p4aj9rk`:

- `c78686a4`: exact header/account/health fast validation in 797 ms; missing target sent zero movement and paused.
- `10ba4b03`: reviewed 300 px camera turn reacquired the next target, approached 11→10→8→3 m, and released on disappearance. 6.394 s local course; HP 3953/4015 unchanged.
- `cf734adc`: read-only OCR comparison, zero gameplay inputs. Saved frame 240009531 visibly reads 25 m. Broad 110×65 crop failed; 70×32 crop correctly read `25m`. Occluded frame 240009527 did not produce a valid distance and remains rejected.
- `e1a4f048`: tight crop live read 21 m then 20 m; high target stopped movement and verified inventory pause.

Two target transitions were previously verified at full frames 9399 and 9420. The attempt was reset after height loss; no exam reward or Act II completion is claimed. Camera and OCR fixes are live-validated, but automatic whole-course completion is not. No native rebuild, application restart, RDP restart, extra death, resin or item expenditure occurred during this fix.

Automated regression results are saved in `artifacts/exam-fast-full-tests.log`. Unrelated native navigation and combat experiments are excluded from this publication candidate.
