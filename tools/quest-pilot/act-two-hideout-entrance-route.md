# Raptor hideout entrance: observed route, not timing replay

Session `mvcuzen8-drrh7eb3gqe`; reconstructable observations and actual inputs are in `artifacts/hideout-entrance-history.json`. Coordinates from this fogged region are unreliable and must not be used as route positions. Headings below are recorded camera headings. Higher/Lower is the quest indicator, not a measured altitude.

| Segment | Recorded entry and exit | Required local verification |
|---|---|---|
| Springvale road | 1274:168m, heading28; road alignment1291:176.5; 1308:136m, heading173 | Full4015, exact hideout objective, grounded, no enemies; fresh visible road |
| Road bend | 1313:135m heading142.5 to1320:110m;1330:89m heading141.5 | Same road bend and decreasing distance after every bounded batch |
| Foot of rising ground | 1335:89m heading124;1337:85m;1349:Higher58m heading123.5 | Visible grounded corridor; no climb contact. Historical W batches are upper bounds only |
| Lower approach | 1359:Higher56m heading114.5 to1365:Higher41m heading114 | Fresh terrain must reconnect before resuming. Later37–51m wandering was not a validated direct route |
| Low shelf | 1509:Higher37m heading105.5;1519:Higher35m heading105 after one reviewed shelf hop;1526:Higher30m heading114 | Reidentify low shelf, safe upper landing, and exact ground controls; never jump at an unmatched wall |
| Proven upper climb | 1633:Higher30m heading108;1635 wall contact;1641:Higher29m heading93.5;1648:87.5;1655:80;1660:Higher30m heading78, ground returned | Visible stamina reserve and measured crest ascent between local batches. Stop on unchanged landmark, lost arc or health. Old images no longer retained; ledger alone does not establish current wall identity |
| Upper grass ledge | 1664:Higher28m heading78;1665 camera36;1672:Higher30m heading114.5;1677 aligned94 | Reidentify upper grass and safe footing before onward motion |
| Entrance slope | 1678:Higher29m to1681:Higher20m heading93;1691:Higher19m to1700:Higher11m;1706:Higher9m | Full4015, grounded, visible slope and decreasing distance; stop before a changed height/terrain state |
| Door turn | 1712:Higher9m heading30;1714:Higher5m;1721:3m heading3 | Exact visible entrance, then exact F Raptor's Hideout prompt |
| Enter | 1743:3m; receipt d8b6bfa24f404c4a91600d6147ab697c →1744 entrance panel | F60 with1200ms settling, verify entrance panel before Start |

## Current divergence, 2026-10-18 01:35 UTC

First exact input divergence is after the long road bend: current2035 reached94m, while original1330 reached89m. The original next segment used camera -180 and two W600 to85m; current receipt0dbe0cfd instead used A800 twice, camera -250, then W600 four times to2046:82m. Current2058 then contacted a low wall atHigher62m, whereas original1347 passedHigher62m grounded atheading123.5. These are **different routes**, despite similar quest distance.

Current low wall was successfully crested with measured stamina355pixels/60px extent at2080, oneW600 at2086, then ground movement to2092:Higher59m. Fresh2108 confirms standing on a grass ledge between a tree and rock wall, full4015. Map-close2101 lacked ground controls because of HUD fade; no movement was sent from that invalid witness. Camera-only2115 inspected the valley side. No claim of reconnection to the old upper climb yet.

Next: align camera to the recorded lower-approach heading about114–124, inspect visible corridor and height. Only resume a segment after entry matching, and verify exit using fresh objective distance, controls, health and landmark. Do not replay old wandering/shelf timings or equate distance with position.

## Verified return, 2026-10-18 02:08 UTC

The unreconnected 59m detour was retired with a Springvale teleport (2179). New return: 2189 at168m heading28, road batches2201/2213/2225 to120m, 2237 at95m, 2248 at71m, 2258 at51m, 2267 at39m. Camera2272 exposed the low shelf;2278 at38m heading103; reviewed hop2283 reached35m. The next movement contacted a different wall at2290 heading174, so this is not the old wall by identity. Climb proof2315->2321 moved the same crest junction fromy122 toy181, then2328 toy493; arc338/362pixels over60px. Six total600msW climbed to2334 grounded34m. Camera2339 aligned upper grass, sixW800 reached2349 at14m heading94. All health4015/4015.

Entrance segment reconnected visually:2366 at11m,2372 at10m afterW600 andleftcamera640. Golden entrance marker was visible to the left. Camera-280 andtwoW800 reached2379 at5m;W600 to2384 at2m;W400 to2389 at1m with exactF Raptor's Hideout. Receiptf81fd1398b7b42efa2035d7c4f97aadc usedF60 and1200mssettle to2394 verified entrance panel. No damage, deaths, resin, EXP reward or application restart on this return. Timings remain upper bounds and each landmark must be freshly verified.
