'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');
const panel = require(path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot/combat-statue-panel.js'));
const fixture = require('./combat-statue-panel.fixture.json');
const clone = value => JSON.parse(JSON.stringify(value));

// Retained OCR is real; clocks/stamps below are explicitly injected inert test data.
function frame(kind = 'panel', id = 1, now = 100000) {
    const o = clone(fixture[kind]);
    o.session = 'inert-panel-test'; o.frameId = id; o.timestamp = now;
    o.hud.captureStamp = { session: o.session, frameId: id, capturedAt: now - 100, source: 'game-capture-start' };
    if (kind === 'world') { o.hud.enemyBars = []; o.hud.health = {current: 1001, max: 1001}; }
    return o;
}

// A native adapter must supply the private owned-roster check and revalidate every actual input.
function harness(options = {}) {
    let now = 100000, id = 1, clicks = 0, closes = 0, releases = 0, observations = 0;
    const api = {
        now: () => now,
        checkStop: () => { if (options.stop && clicks >= options.stop) throw Error('STOP'); },
        sleep: async ms => { now += ms; },
        release: async () => { releases++; if (options.releaseFails) throw Error('release failed'); },
        panelSourceReady: () => options.rosterBound !== false,
        clickLisaPortrait: async (o, permit) => {
            assert.equal(permit.frameId, o.frameId); assert.deepEqual([permit.x, permit.y], [658, 160]);
            clicks++; if (options.clickFails) throw Error('uncertain click');
        },
        closeStatuePanel: async () => { closes++; }
    };
    async function observe() {
        observations++; id++;
        const o = frame(closes ? 'world' : 'panel', id, now);
        if (options.mutate) options.mutate(o, {clicks, closes, observations, now});
        return o;
    }
    return { api, observe, initial: frame(), counts: () => ({clicks, closes, releases, observations}) };
}

test('retained fourth Lisa card selects only658,160 with original account and reserve', () => {
    const o = frame(); const p = panel.permission(o, 100000, o.session, 0);
    assert.deepEqual({slot:p.slot,x:p.x,y:p.y,power:p.restorativePower}, {slot:4,x:658,y:160,power:10000});
});

test('retained exact fixed-denominator slash OCR substitution remains bounded', () => {
    const o = frame(); const row = o.ocr.find(r => /^Restorative Power:/.test(r.text));
    Object.assign(row, fixture.alternativePowerRow);
    assert.equal(panel.permission(o, 100000, o.session, 0).restorativePower, 9598);
    row.text = 'Restorative Power: 9598 79999';
    assert.equal(panel.permission(o, 100000, o.session, 0), null);
});

test('capture-start age and matching source identity are mandatory', () => {
    const mutations = [
        o => { delete o.hud.captureStamp; },
        o => { o.hud.captureStamp.capturedAt = 98999; },
        o => { o.hud.captureStamp.capturedAt = 100001; },
        o => { o.hud.captureStamp.source = 'observation-complete'; },
        o => { o.hud.captureStamp.frameId = 2; },
        o => { o.hud.captureStamp.session = 'another-session'; },
        o => { o.frameId = 0; },
        o => { o.timestamp = 100001; }
    ];
    for (const mutate of mutations) { const o = frame(); mutate(o); assert.equal(panel.permission(o,100000,o.session,0),null); }
    const o = frame(); assert.equal(panel.permission(o,100000,o.session,1),null);
});

test('missing, duplicated, moved or changed fourth card never selects another portrait', () => {
    const mutations = [
        o => { o.ocr = o.ocr.filter(r => !/^Lv\. 4$/.test(r.text)); },
        o => { o.ocr.push(clone(o.ocr.find(r => /^Lv\. 4$/.test(r.text)))); },
        o => { o.ocr.find(r => /^Lv\. 4$/.test(r.text)).x = 448; },
        o => { o.ocr.find(r => /^Lv\. 4$/.test(r.text)).text = 'Lv. 5'; },
        o => { o.ocr.find(r => /^Lv\. 20$/.test(r.text)).text = 'Lv. 19'; }
    ];
    for (const mutate of mutations) { const o = frame(); mutate(o); assert.equal(panel.permission(o,100000,o.session,0),null); }
});

test('wrong account, modal, reserve depletion and wrong screen refuse all clicks', async () => {
    const mutations = [
        o => { o.ocr.find(r => /UID/.test(r.text)).text = 'UID: 123456789'; },
        o => { o.ocr.push({text:'Confirm',x:800,y:600,width:100,height:30}); },
        o => { o.ocr.find(r => /^Restorative Power:/.test(r.text)).text = 'Restorative Power: 0/10000'; },
        o => { o.hud.world = true; },
        o => { o.hud.bigMap = true; }
    ];
    for (const mutate of mutations) {
        const h = harness(); mutate(h.initial);
        const r = await panel.run(h.initial,h.api,h.observe);
        assert.equal(r.healthVerified,false); assert.equal(h.counts().clicks,0); assert.equal(h.counts().releases,1);
    }
});

test('unbound roster cannot use a retained fourth-card layout as native authority', async () => {
    const h = harness({rosterBound:false}); const r = await panel.run(h.initial,h.api,h.observe);
    assert.equal(r.healthVerified,false); assert.equal(h.counts().clicks,0);
});

test('three distinct panel sources and fresh numeric Lisa health complete the bounded operation', async () => {
    const h = harness(); const r = await panel.run(h.initial,h.api,h.observe);
    assert.equal(r.status,'completed'); assert.equal(r.healthVerified,true);
    assert.deepEqual(r.health,{current:1001,max:1001});
    assert.deepEqual(h.counts(),{clicks:3,closes:1,releases:1,observations:4});
    assert.equal(r.portraitClickAttempts,3); assert.equal(r.paused,undefined);
});

test('a stale post-click source stops without replay or panel close', async () => {
    const h = harness({mutate:o => { o.hud.captureStamp.capturedAt -= 2000; }});
    const r = await panel.run(h.initial,h.api,h.observe);
    assert.equal(r.healthVerified,false); assert.deepEqual(h.counts(),{clicks:1,closes:0,releases:1,observations:1});
});

test('an uncertain click is never retried', async () => {
    const h = harness({clickFails:true}); const r = await panel.run(h.initial,h.api,h.observe);
    assert.equal(r.healthVerified,false); assert.equal(h.counts().clicks,1); assert.equal(h.counts().closes,0);
});

test('STOP after the first click releases and sends no additional input', async () => {
    const h = harness({stop:1}); const r = await panel.run(h.initial,h.api,h.observe);
    assert.equal(r.healthVerified,false); assert.equal(h.counts().clicks,1); assert.equal(h.counts().closes,0);
});

test('below95% is recorded as observed health without a healing-success claim', async () => {
    const h = harness({mutate:(o,s) => { if (s.closes) o.hud.health.current = 900; }});
    const r = await panel.run(h.initial,h.api,h.observe);
    assert.equal(r.status,'stopped'); assert.equal(r.healthVerified,false); assert.equal(r.health.current,900);
});

test('wrong maxHP, roster, enemy or unknown ground state cannot verify recovered Lisa', () => {
    const mutations = [
        o => { o.hud.health = {current:4015,max:4015}; },
        o => { o.ocr.find(r => r.text.trim()==='Lisa').text = 'Barbara'; },
        o => { o.hud.enemyBars = [{x:1,y:1,width:50,height:5}]; },
        o => { o.hud.groundControls = false; }
    ];
    for (const mutate of mutations) { const o = frame('world'); mutate(o); assert.equal(panel.worldHealth(o,100000,o.session,0),null); }
});

test('release failure overrides a nominal completed health result', async () => {
    const h = harness({releaseFails:true}); await assert.rejects(panel.run(h.initial,h.api,h.observe),/release failed/);
});

test('larger frame IDs cannot renew reused or regressed capture/completion clocks', async () => {
    const cases = [[99900,100000],[99850,99980],[99900,100700],[99950,100000]];
    for (const [capturedAt,completedAt] of cases) {
        const h = harness({mutate:(o,s) => {
            if (s.observations === 1) { o.hud.captureStamp.capturedAt = capturedAt; o.timestamp = completedAt; }
        }});
        const r = await panel.run(h.initial,h.api,h.observe);
        assert.equal(r.healthVerified,false); assert.equal(h.counts().clicks,1);
        assert.equal(h.counts().closes,0); assert.equal(h.counts().releases,1);
    }
});

test('two complete UID readings refuse panel and world evidence while partial fragments confer no identity', () => {
    for (const kind of ['panel','world']) {
        const o = frame(kind), uid = clone(o.ocr.find(r => /UID/.test(r.text)));
        uid.text = 'UID: 123456789'; uid.x = 800; o.ocr.push(uid);
        assert.equal(panel.permission(o,100000,o.session,0),null);
        assert.equal(panel.worldHealth(o,100000,o.session,0),null);
    }
    const o = frame(); o.ocr.push({text:'69330',x:1684,y:1050,width:60,height:29});
    assert.equal(panel.permission(o,100000,o.session,0).slot,4);
    o.ocr = o.ocr.filter(r => !/^UID/.test(r.text));
    assert.equal(panel.permission(o,100000,o.session,0),null);
});
