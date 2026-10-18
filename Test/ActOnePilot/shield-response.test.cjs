const test = require('node:test'), assert = require('node:assert/strict');
const policy = require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/shield-response.js');
function scene() {
    const fresh = { session: 's', frameId: 10, timestamp: 1000 };
    const cap = { ...fresh, partyVerified: true, primitiveTested: true, ready: true,
        cooldownReady: true, energyRequired: true, energyReady: true,
        rangeVerified: true, facingVerified: true, targetId: 'wood1', element: 'Pyro' };
    return { ...fresh, now: 1100, focusVerified: true, sessionVerified: true,
        healthRatio: 1, healthLossRatio: 0, remainingActionMs: 4000,
        target: { ...fresh, id: 'wood1', visible: true, tracked: true, confidence: .96,
            kind: 'material', material: 'wood', shieldVisible: true },
        capabilities: [{ ...cap, id: 'Amber.Q', exposureMs: 1500 },
            { ...cap, id: 'Amber.E', energyRequired: false, exposureMs: 8500 },
            { ...cap, id: 'Amber.charged', energyRequired: false, exposureMs: 3000 }] };
}
test('wood selects short ready Pyro burst, falls back to tested charged shot without energy', () => {
    const c = scene(); assert.equal(policy.decide(c).capability, 'Amber.Q');
    c.capabilities[0].energyReady = false;
    assert.equal(policy.decide(c).capability, 'Amber.charged');
    c.capabilities[2].facingVerified = false;
    assert.equal(policy.decide(c).action, 'retreat'); // delayed decoy exceeds exposure budget
});
test('unknown, stale, interrupted, unhealthy, unready or untested means no attack', () => {
    for (const mutate of [c=>c.target.material='stone', c=>c.now=1801,
        c=>c.target.confidence=.89, c=>c.target.tracked=false, c=>c.interrupted=true,
        c=>c.healthLossRatio=.051, c=>c.healthRatio=.94,
        c=>c.capabilities.forEach(a=>a.ready=false),
        c=>c.capabilities.forEach(a=>a.primitiveTested=false),
        c=>c.capabilities.forEach(a=>a.targetId='other')]) {
        const c=scene(); mutate(c); assert.equal(policy.decide(c).action,'retreat');
    }
});
test('two attempts or one established ineffective application stops unchanged retries', () => {
    assert.equal(policy.decide(scene(),{attempts:2}).action,'retreat');
    assert.equal(policy.decide(scene(),{attempts:1,lastOutcome:'no-effect'}).action,'retreat');
});
test('elemental bubbles choose available starter counters, never same-element attacks', () => {
    for (const [element,expected] of [['Cryo','Pyro'],['Hydro','Cryo'],['Pyro','Electro'],['Electro','Pyro']]) {
        const c=scene(); c.target={...c.target,kind:'barrier',family:'AbyssMage',element};
        const cap=c.capabilities[0];c.capabilities=['Pyro','Cryo','Electro','Anemo'].map(e=>({...cap,id:e,element:e}));
        assert.equal(policy.decide(c).element,expected);
    }
});
test('burning establishes application only; positive tracked break evidence allows damage', () => {
    const c=scene(),before={...c.target,timestamp:900};
    const after={...c.target,burningOnShieldVerified:true};
    assert.deepEqual(policy.verify(before,after,c),{state:'burning',damageRotationAllowed:false});
    Object.assign(after,{shieldVisible:false,bodyVisible:true,breakAnimationVerified:true,unshieldedPoseVerified:true});
    assert.equal(policy.verify(before,after,c).damageRotationAllowed,true);
    after.id='other';assert.equal(policy.verify(before,after,c).state,'unknown');
});
test('missing bar, damage number, target loss and zero gauge alone do not prove removal', () => {
    const c=scene(),before={...c.target,timestamp:900};
    for(const extra of [{shieldVisible:false},{damage:123},{visible:false},{shieldFraction:0}])
        assert.equal(policy.verify(before,{...c.target,...extra},c).damageRotationAllowed,false);
});
test('barrier progress requires same target/element and tracked comparable gauge', () => {
    const c=scene(),before={...c.target,timestamp:900,kind:'barrier',element:'Cryo',gaugeTracked:true,shieldFraction:1};
    const after={...before,timestamp:1000,shieldFraction:.7};
    assert.equal(policy.verify(before,after,c).state,'reduced');
    after.element='Hydro';assert.equal(policy.verify(before,after,c).state,'unknown');
});
