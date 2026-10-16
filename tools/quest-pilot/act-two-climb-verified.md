# Act II upper-shelf climbing validation — 2026-10-16

Act II remains locked at AR9. This change handles two observed low ledges on the License to Glide approach from Temple of the Lion; it does not claim quest completion or authorize arbitrary cliffs.

The controller allows camera-only inspection while safely latched, and at two recorded ledge anchors accepts 600 ms climbing holds after fresh health, identity, location, threat and stamina evidence. A single explicitly reviewed 600 ms probe can reveal a hidden gauge. The same-capture reader uses a narrow yellow color range and component geometry; missing or malformed gauges never imply full stamina. Its 180-pixel/45-pixel-extent floor is a conservative image proxy, not a calibrated stamina percentage. Capture derivatives are disposed. Normal navigation remains grounded, all inputs are bounded and released, and changed evidence stops the batch.

Live evidence in session mv9t341i-eft9p4aj9rk, child11256/RDP7/game39136:

- Temple teleport7737 then upper shelf7775/7790 reduced132m to82m. The first ledge7804 required2500ms total upward input, followed by verified standing7855. Kaeya remained3981/4015HP.
- The first exact-color crop missed the shifted gauge. Expanded crop7837 correctly read309pixels; daylight7889 altered its color, so a bounded range replaced exact equality. Live7894 read316pixels with the required narrow arc shape.
- Second low ledge7883 required1200ms upward input. Subsequent request fda3dffde63e4093bac373527d3a6ca9 correctly sent no further climb when fresh7905 was already grounded; standing7908 verified. No falling or damage occurred.
- Upper travel reached51m at7923. Its taller wall was not assumed climbable. One reviewed60ms release c34d9c854011423a834e34bd3c2f0576 returned to nearby grass7928, unchangedHP. A Common Chest was then approached separately.

Validation: all1571 tracked JavaScript regressions plus the new climb/camera tests passed in38.722s against the exact publication candidate, excluding the uninstalled native-map and unvalidated shield-probe experiments. Recorded fixtures cover the two ledges, visible gauge and safe base release; negative cases cover absent/low/malformed stamina, adjacent retired cliff, low health, excessive holds and guaranteed release. No native build or application/RDP restart was needed. No resin, food or premium currency was consumed by these climbs.
