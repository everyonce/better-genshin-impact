const test = require('node:test');
const assert = require('node:assert/strict');
const policy = require('../../BetterGenshinImpact/User/JsScript/UnexpectedPowerPilot/policy.js');

const prompt = (text, x = 900, y = 220) => ({ text, x, y });
const journal = (title = 'Unexpected Power', status = 'In Progress') => [
    { text: title, x: 1200, y: 120 }, { text: status, x: 1200, y: 165 }
];
test('recognizes the live wrapped hold tutorial without accepting partial or unrelated text', () => {
    const rows = [prompt('Hold E to charge skills for increased', 757, 181), prompt('E', 665, 195), prompt('power', 941, 211)];
    assert.equal(policy.classify(rows).action.type, 'hold_skill');
    assert.equal(policy.classify(rows.slice(0, 2)).kind, 'unknown');
    assert.equal(policy.classify([rows[0], prompt('power', 941, 800)]).kind, 'unknown');
});
test('allows only the matching adjacent key icon seen in live OCR', () => {
    assert.equal(policy.classify([prompt('Q Press Q to unleash Elemental Burst')]).action.type, 'burst');
    assert.equal(policy.classify([prompt('E Press E to unleash Elemental Skill')]).action.type, 'tap_skill');
    assert.equal(policy.classify([prompt('Q Press E to unleash Elemental Skill')]).kind, 'unknown');
    assert.equal(policy.classify([prompt('Use Q Press Q to unleash Elemental Burst')]).kind, 'unknown');
});
function fixture(sequence) {
    let clock = 1000, index = 0;
    const calls = [], saved = [];
    const api = {
        now: () => clock,
        observe: async () => sequence[Math.min(index++, sequence.length - 1)],
        closeJournal: async () => calls.push(['closeJournal']), openJournal: async () => calls.push(['openJournal']),
        hold: async (key, ms) => calls.push(['hold', key, ms]), wait: async ms => { calls.push(['wait', ms]); clock += ms; },
        assertReady: async () => calls.push(['assertReady']),
        release: () => calls.push(['release']), saveStatus: x => saved.push(structuredClone(x))
    };
    return { api, calls, saved };
}

test('recognizes only exact bounded tutorial text after punctuation normalization', () => {
    assert.deepEqual(policy.classify([prompt('  PRESS E, to unleash Elemental Skill!  ')]).action,
        { type: 'tap_skill', key: 'E', ms: 60 });
    assert.equal(policy.classify([prompt('Hold E to unleash Elemental Skill')]).action.type, 'hold_skill');
    assert.equal(policy.classify([prompt('Press Q to unleash Elemental Burst')]).action.type, 'burst');
    assert.equal(policy.classify([prompt('Press E to unleash Elemental Skill and defeat the enemy')]).kind, 'unknown');
    assert.equal(policy.classify([prompt('Press E to unleash Elemental Skill'), prompt('Press Q to unleash Elemental Burst')]).reason, 'ambiguous_prompt');
    assert.equal(policy.classify([prompt('Press E to unleash Elemental Skill', 1500)]).kind, 'unknown');
});

test('recognizes journal heading plus nearby In Progress without selection metadata', () => {
    assert.equal(policy.classify(journal()).kind, 'targetJournal');
    assert.equal(policy.classify(journal('Unexpected Power', 'Quest Completed')).kind, 'completed');
    assert.equal(policy.classify(journal('Forest Rendezvous')).kind, 'nextJournal');
    assert.equal(policy.classify([{ text: 'Forest Rendezvous', x: 1000, y: 120 }]).kind, 'unknown');
    assert.equal(policy.classify([...journal(), { text: 'Forest Rendezvous', x: 1200, y: 190 }]).reason, 'ambiguous_journal');
    assert.equal(policy.classify([{ text: 'Unexpected Power', x: 1200, y: 120 }, { text: 'Quest Completed', x: 1200, y: 150 }]).kind, 'completed');
});

test('validates exact prompt action pairs and rejects global E/Q or duration escalation', () => {
    const state = policy.classify([prompt('Hold E to unleash Elemental Skill')]);
    assert.equal(policy.validateAction(state.action, state).ok, true);
    for (const action of [{ type: 'burst', key: 'Q', ms: 60 }, { type: 'hold_skill', key: 'E', ms: 1201 },
        { type: 'tap_skill', key: 'E', ms: 60 }]) assert.equal(policy.validateAction(action, state).ok, false);
    assert.equal(policy.validateAction({ type: 'burst', key: 'Q', ms: 60 }, { kind: 'unknown' }).ok, false);
});

test('runner confirms target journal, closes it, and releases after each bounded action', async () => {
    const f = fixture([journal(), [prompt('Press E to unleash Elemental Skill')], [{ text: 'Quest Completed', x: 900, y: 200 }, { text: 'Unexpected Power', x: 900, y: 230 }]]);
    const result = await policy.run(f.api);
    assert.equal(result.status, 'completed');
    assert.deepEqual(f.calls.filter(c => c[0] === 'hold'), [['hold', 'E', 60]]);
    assert.equal(f.calls[0][0], 'assertReady');
    assert.equal(f.calls[1][0], 'closeJournal');
    assert.equal(f.calls.filter(c => c[0] === 'release').length, 2);
    assert.deepEqual(f.saved.at(-1).actions.filter(a => a.type === 'tutorialAction').map(a => a.detail), ['tap_skill']);
    assert.equal(f.saved.some(s => s.phase === 'action_started'), true);
    assert.equal(result.interventions.length, 0);
});

test('runner refuses to act before target confirmation and stops before the next quest', async () => {
    const f = fixture([journal('Forest Rendezvous')]);
    assert.equal((await policy.run(f.api)).stoppedReason, 'next_quest_requires_target_confirmation');
    assert.deepEqual(f.calls, [['release']]);
    const g = fixture([journal(), [prompt('Press E to unleash Elemental Skill')], journal('Forest Rendezvous')]);
    const result = await policy.run(g.api);
    assert.equal(result.stoppedReason, 'next_quest_reached_after_target');
    assert.equal(g.calls.filter(c => c[0] === 'hold').length, 1);
});

test('runner caps unchanged-prompt retries, delays each retry, and fails closed on unknown OCR', async () => {
    const f = fixture([journal(), ...Array(5).fill([prompt('Press E to unleash Elemental Skill')])]);
    const stalled = await policy.run(f.api);
    assert.equal(stalled.stoppedReason, 'prompt_stalled');
    assert.equal(f.calls.filter(c => c[0] === 'hold').length, 3);
    assert.equal(f.calls.filter(c => c[0] === 'wait' && c[1] >= 3000).length, 2);
    const g = fixture([journal(), ...Array(5).fill([{ text: 'A random narrative line', x: 900, y: 200 }])]);
    assert.equal((await policy.run(g.api)).stoppedReason, 'unknown_state');
    assert.equal(g.calls.some(c => c[0] === 'hold'), false);
});

test('runner releases held input on action failure and records the stop reason', async () => {
    const f = fixture([journal(), [prompt('Hold E to unleash Elemental Skill')]]);
    f.api.hold = async () => { f.calls.push(['hold']); throw new Error('input_failure'); };
    const result = await policy.run(f.api);
    assert.equal(result.stoppedReason, 'input_failure');
    assert.equal(f.calls.at(-1)[0], 'release');
    assert.equal(f.saved.at(-1).stoppedReason, 'input_failure');
});

test('runner observes the two minute budget before further interaction', async () => {
    const f = fixture([journal(), [prompt('Press E to unleash Elemental Skill')]]);
    f.api.wait = async ms => { f.calls.push(['wait', ms]); };
    f.api.hold = async () => { f.api.now = () => 121001; };
    const result = await policy.run(f.api);
    assert.equal(result.stoppedReason, 'duration_limit');
    assert.equal(f.calls.filter(c => c[0] === 'hold').length, 0);
});

test('verifiedWorld waits for three frames, opens journal once, and sends no combat input', async () => {
    const f = fixture([journal(), { mode: 'verifiedWorld', rows: [] }, { mode: 'verifiedWorld', rows: [] },
        { mode: 'verifiedWorld', rows: [] }, journal()]);
    const result = await policy.run(f.api);
    assert.equal(result.stoppedReason, 'target_journal_reconfirmed');
    assert.equal(result.status, 'stopped');
    assert.equal(f.calls.filter(c => c[0] === 'openJournal').length, 1);
    assert.equal(f.calls.some(c => c[0] === 'hold'), false);
    assert.deepEqual(result.interventions, []);
});

test('world HUD cannot replace initial target quest confirmation', async () => {
    const f = fixture([{ mode: 'verifiedWorld', rows: [prompt('Press E to unleash Elemental Skill')] }]);
    const result = await policy.run(f.api);
    assert.equal(result.status, 'stopped');
    assert.equal(result.stoppedReason, 'target_journal_not_confirmed');
    assert.equal(f.calls.some(c => ['hold', 'openJournal', 'closeJournal'].includes(c[0])), false);
});

test('readiness failure blocks every input and records no completion', async () => {
    const f = fixture([journal(), [prompt('Press E to unleash Elemental Skill')]]);
    f.api.assertReady = async () => { f.calls.push(['assertReady']); throw new Error('focus_lost'); };
    const result = await policy.run(f.api);
    assert.equal(result.stoppedReason, 'focus_lost');
    assert.equal(f.calls.some(c => ['closeJournal', 'openJournal', 'hold'].includes(c[0])), false);
});

test('retry uses fresh OCR after the delay and follows a changed prompt', async () => {
    const f = fixture([journal(), [prompt('Press E to unleash Elemental Skill')],
        [prompt('Press E to unleash Elemental Skill')], [prompt('Press Q to unleash Elemental Burst')],
        [{ text: 'Unexpected Power', x: 900, y: 200 }, { text: 'Quest Completed', x: 900, y: 230 }]]);
    const result = await policy.run(f.api);
    assert.equal(result.status, 'completed');
    assert.deepEqual(f.calls.filter(c => c[0] === 'hold'), [['hold', 'E', 60], ['hold', 'Q', 60]]);
    assert.equal(f.calls.filter(c => c[0] === 'wait' && c[1] === 3000).length, 1);
});

test('next journal after target confirmation is recorded as completion and never acted on', async () => {
    const f = fixture([journal(), [prompt('Press E to unleash Elemental Skill')], journal('Forest Rendezvous')]);
    const result = await policy.run(f.api);
    assert.equal(result.status, 'completed');
    assert.equal(result.stoppedReason, 'next_quest_reached_after_target');
    assert.equal(f.calls.some(c => c[0] === 'hold' && c[1] !== 'E'), false);
});
