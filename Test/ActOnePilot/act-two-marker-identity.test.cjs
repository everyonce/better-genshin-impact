const test=require('node:test'),assert=require('node:assert/strict'),fs=require('fs');
const source=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
const match=source.match(/function actTwoSceneMarkerCandidate\(x,y\) \{[^\n]+\}/);assert(match);
const candidate=eval('('+match[0]+')');
test('recorded scene destinations exclude the party ability HUD and network ping',()=>{
 for(const p of require('./act-two-marker-identity.fixture.json').candidates)assert.equal(candidate(p.x,p.y),p.sceneCandidate,p.identity);
});
test('scene identity alone never invents distance or authorizes forward flight',()=>{
 const exam=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-exam.js');
 assert.equal(exam.distance([{text:'Space'},{text:'UID:693306810'}]),null);
 for(const p of [[NaN,450],[960,Infinity],[319,450],[1800,400],[1615,500]])assert.equal(candidate(...p),false);
});
