# Bounded exam flight and recovery

The timed Amber exam exposed three controller defects: the abandonment modal still shows HP, Space-only airborne controls can lose party-name OCR, and objective OCR occasionally adds punctuation. The exam path now recognizes the exact modal immediately, permits pause-only input from Space + valid HP + original UID, uses a 12-second pause deadline, and normalizes punctuation while requiring the complete objective text.

The Amber interaction crop now checks Amber rather than falling through to Kaeya. Retry dialogue and the previously verified return ledges remain guarded by exact account, position, health and selected interaction evidence.

Fast deployment recovery preserves the successful single-Space primitive, checks menu fade locally and never toggles already-open wings. Stationary and moving double-Space launch attempts are tested but have NOT themselves produced verified deployment; the successful in-game sequence is moving launch, immediate pause, then one fast recovery Space. Do not describe standalone launch as working.

A bounded course controller reads Space, HP, the gold target and its distance locally, corrects heading, and stops on missing/unsafe evidence, nonprogress or an eight-second deadline. A near-distance then distant-target transition is only a passage candidate. It requires later course evidence; airborne duration is not completion. The original 37px template recognized the marker but lost it during motion; a 21px center crop was exercised successfully on the subsequent approach. The controller now keeps forward held through short recognition cycles and releases in finally.

Live evidence (RDP7, UID693306810, session mv9t341i-eft9p4aj9rk):
- e61d634c: one fast recovery Space opened wings at9218; HP3953/4015.
- b9f1ce2f and f66b1ed4: exact abandonment inspection completed8.046s and9.311s, replacing the prior69.279s failure. 8f3ef8d3 recovery returned to Amber in8.437s.
- d021b46c: airborne pause recovered in5.551s without app or RDP restart after the prior70.695s failure.
- 2c9462af: corrected Amber crop allowed retry dialogue and fresh trial9201.
- 87e870d7: local target sequence29m ->9m in8.535s, nine400ms movement intervals, HP unchanged; NO ring passage. This was the earlier intermittent-input implementation.
- 0fa434d2: continuous controller sent zero movement when the target was overhead/outside its corridor. Successful continuous traversal remains pending.

Validation: 1602 JavaScript tests passed, zero failures,38.224s. Log: artifacts/exam-course-full-tests.log. Includes recorded modal, faded-party flight and punctuation fixtures, bounded movement/release/pause tests, Amber retry tests and reviewed ledge regressions. The Python test runner's final console summary hit a Windows encoding error AFTER Node returned zero; the saved log records the successful test result. No C# changes or native rebuild.

Act II remains locked at AR9, last exact200/1300. No exam reward or new resin spending. No new death since the earlier exam death8238. Current course work continues; this is not a completion report.
