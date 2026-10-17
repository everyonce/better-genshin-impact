# Fixed lower-climb local mission

Status: offline regression tested; live validation and speedup measurement pending.

`actTwoLowerClimb` combines only the seven previously observed phases from
`middle-ascent` through `balcony-align` into one bounded mission. It stops before
landing review. It cannot start at the upper wall or balcony ladder, mount the
wall, release the climb, jump, or navigate to the ladder. The existing known-good
runtime remains installed until a separately verified deployment.

The one-use `act-two-lower-climb-request.json` contains exactly:

```json
{"recipe":"lower-climb-seven-v1","reviewed":true,"session":"FRESH_SESSION","frameId":0,"witnessFrameId":0,"createdAt":0}
```

Replace the placeholders only after fresh inventory/account verification and a
matching lower-wall witness: full Kaeya health, correct riddle objective, Higher
23m, recorded pose and adequate same-frame stamina. The witness precedes the
inventory frame, belongs to that session and is at most ten minutes old. The plan
is at most two minutes old and consumed before unpausing. Do not reuse it after a
failure. Submit through the existing `act-one-command.py questStep` path with
`--step actTwoLowerClimb`; allow 120 seconds for the terminal receipt because the
local mission deadline is 90 seconds plus bounded pause protection. The generic
70-second result wrapper is too short for this mission's worst case.

Every pulse retains fresh recognition, field/session/focus/cancellation checks,
bounded holds and key release. Only one stationary stamina reread is allowed for
an ambiguous contour; numeric low stamina or changed pose cannot trigger retries.
No screenshot persistence rules were changed. Eliminating intermediate menu
captures naturally removes their PNG/OCR cost. Final pause is verified by the
existing pause protector; menu presence alone is not success.

Timings distinguish input, settle, recognition, phase transitions, ambiguity,
guard failures and the required final visual review. Failure evidence records
the last frame, screenshot path, pose and HUD, whether an action threw, and
whether its resulting state remains unverified. No pulse is automatically replayed.

The preceding seven-request replay took 95.547 seconds. Its measured internal
request gaps and intermediate entry/pause overhead totaled 43.509 seconds. This
is a reducible overhead budget, **not a measured speedup**; live comparison remains
pending. Do not replay a completed ascent just to benchmark it.
