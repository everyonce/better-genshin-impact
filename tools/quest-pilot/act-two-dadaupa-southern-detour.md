# Dadaupa southern detour checkpoint

The southern exploration corridor now includes y=1400..1449 within x=-1500..-1300. Other navigation limits remain unchanged. The previous y=1400 rejection test now checks y=1399; a dedicated test checks the new southern route and both longitude boundaries.

Live request `mission-a7629712a5c345deb9c871b9d61ae465` reached both southern detour points and ended at(-1429.03,1420.99), full4015HP, verified inventory pause494. Duration45949ms;16movement holds,9turns,input10625ms. This is route arrival, not a waypoint unlock or Adventure EXP reward.

The eastern continuation stopped at a Lv16 road encounter. Three subsequent bounded prototype probes made five camera corrections and four450ms approach steps; they made zero attacks or skill casts and ended fullHP. The prototype stopped on extra contours, occlusion and its movement limit. It is not a validated combat solution and is not included in this publication. Retained candidate code/tests are under artifacts/dadaupa-east-route and untracked southern-enemy test files.

Fresh map539 confirmed resin200/200 and the locked waypoint. Existing Lion teleport4891be30 returned to(-1427.43,1661.82), fullHP542/543, verified inventory545. Adventure EXP gained by this detour:0. Resin spent:0. No build, application/RDP/script restart, death or permanent cleanup.

The western rock-lip line(-1424.8,1458.5)->(-1428,1460) remains retired, as does the old direct northern face(-1430,1495). A distinct upper ridge approach is being inspected from the known road near(-1410,1625). Do not replay either retired line.

Validation: the combined candidate suite passed1907 tests,0failed,40860.2437ms. It includes the corridor change and unpublished defense prototype. The initial old-boundary regression correctly failed, was updated to1399, and passed. A tool-session interruption stopped one intermediate run; the complete final run is recorded in artifacts/dadaupa-east-route/full-tests-final.log.
