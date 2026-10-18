# Recorded camera evidence for field progress

The hideout climb at frames1572→1578 rose visibly, but frame1572 had no minimap position or camera angle. The next movement was rejected despite a named vertical landmark because angle comparison could not run. The character was released onto grass1583 with4015/4015HP; that landing cannot reuse the earlier ascent proof.

`audit-field-camera.ps1` replays the repository's existing CameraOrientationFromGia algorithm against the retained1920x1080 screenshots using the runtime OpenCvSharp assembly and official212x212 minimap crop. It disposes both Mats, records SHA256 hashes, and sends no input. Frames1572 and1578 both measured121degrees. The field planner computes this evidence itself and discards caller-supplied computed headings. The guard uses it only when ordinary angle comparison is unavailable, with exact session/frame/hash validation. It still requires the named measured vertical landmark and unchanged view, or a sufficiently rotated view and reviewed traversable exit. A camera rotation alone remains insufficient.

Validation:13 focused tests pass;1960 canonical tests pass,0 failures,48186.036ms. Live request9084bb27f82e42d2a235f40abb5531ba exercised the replay/planner plumbing with121→64degree evidence and moved onto the grass shelf1605 at full health. The current map was null, so this request does not establish live execution of the guard's fallback branch. That branch has recorded-state regression coverage only. No native rebuild or application restart.

Known limitation retained from the prior progress watchdog: null regional map positions do not establish proximity. Model review must still retire repeated unchanged regional movement. This change does not claim to solve that separate issue.
