const test = require('node:test');
const assert = require('node:assert/strict');
const policy = require('../../BetterGenshinImpact/User/JsScript/UnexpectedPowerPilot/policy.js');
const captures = require('./live-captures.json');

test('recognizes the saved RDP tutorial captures and abstains during the transition', () => {
    for (const capture of captures) {
        const state = policy.classify(capture.rows);
        assert.equal(state.kind, capture.expectedKind, capture.label);
        assert.equal(state.action?.type || null, capture.expectedAction, capture.label);
    }
});

test('recorded prompt sequence advances locally and stops at the selected following quest', async () => {
    const sequence = captures.filter(c => c.expectedKind !== 'unknown');
    let index = 0, clock = 0;
    const inputs = [];
    const result = await policy.run({
        now: () => clock,
        observe: async () => ({ rows: sequence[index++].rows }),
        assertReady() {}, closeJournal: async () => inputs.push('closeJournal'),
        openJournal: async () => inputs.push('openJournal'),
        hold: async (key, ms) => inputs.push([key, ms]),
        wait: async ms => { clock += ms; }, saveStatus() {}, release() {}
    });
    assert.equal(result.status, 'completed');
    assert.equal(result.stoppedReason, 'next_quest_reached_after_target');
    assert.deepEqual(inputs, ['closeJournal', ['E', 60], ['E', 1200], ['Q', 60]]);
    assert.equal(index, sequence.length);
});
