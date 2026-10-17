# Starfell swim stamina diagnosis

Act II remains locked at the last verified AR9,955/1300 checkpoint. These are controller repairs, not Adventure EXP gains.

The native OpenCvSharp replay in `audit-swim-stamina.ps1` uses the live runtime assembly and reads saved images without modifying them. Recorded frames644,722,729 contained no arc in the original crop or wider central search. A visible climbing arc615 validated the color pipeline, not swimming geometry. Widening color thresholds was not supported.

After bounded downward camera preparation, swim entry774 showed the arc outside the original crop during the transition. One stationary800ms reread775 showed a settled, visible arc within the crop. The native strict color mask contained490pixels and two contours: main(30,36,13,64) and detached tip(30,29,8,6), relative to crop(1060,560,80,180). Source PNG SHA256:B4A9BA4D16D400BA25E940FD65C836D68DD24018619137E49422D6DA737BB521. The former exact-one-contour rule rejected this readable arc.

The repair accepts at most one small aligned tip above the main contour, separated by at most3pixels. It returns only the main contour's height; the tip never adds stamina. Existing pixel limits, main-height limits, continuation start40, movement floor25, region, health, identity, focus, session and key-release checks remain. Absent, misaligned, overfragmented and unrelated contours remain unknown. The stationary reread occurs at most once, with no movement while evidence remains unknown.

Camera adjustment itself is bounded and dry-spawn guarded. Grass OCR caused two no-movement stops at749/755; an existing camera-only field routine corrected the view. This manual preparation remains an intervention, and a completely automatic repeatable crossing is not yet established. No native build or application/RDP restart was required.

Regression coverage includes the actual frame775 JSON and native pixel/contour replay. Full canonical suite:1939passed,0failed,40256.9424ms. The new conservative detector's live validation is recorded separately; a passing replay alone is not a live-success claim.

Live validation `baf9dbbe7d214929b11469f4a0640663` completed12bounded600ms inputs with one stationary reread and no unknown-stamina bypass. The endpoint822 was(-1318.28125,2551.45801),remaining distance12.7014,measured arc46pixels,HP4015/4015. Inventory825/controller826 verified the stop. Duration36812ms includes recognition and pause overhead. This validates the repaired first leg; by itself it does not establish dry-shore arrival or autonomous camera setup.

Continuation `b6063e80918647f5b65bc2fa67aaa3cd` used7inputs/4200ms, took20261ms, and regained ground controls835 at(-1313.80469,2547.23047). The existing short bank approach `90cd46a03e744fa9aec8a1fa754f698f` used3inputs/1800ms and verified dry rock-bank844 at(-1307.78125,2541.61719),4015/4015HP, no enemies, and Inventory845/controller846. This crossing and landing is live verified. No EXP, resin, premium currency, food, new fall or death was recorded. The western mountain approach remains unverified beyond previously visited ground; the waypoint is not activated.
