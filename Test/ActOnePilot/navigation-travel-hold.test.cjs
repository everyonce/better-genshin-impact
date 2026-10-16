const test=require('node:test'),assert=require('node:assert/strict');
const m=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/mission.js');
test('ordinary travel uses distance to arrival boundary within existing input ceiling',()=>{
 assert.equal(m.travelHoldMs('Go to the exam point',9,2,5000),800);
 assert.equal(m.travelHoldMs('Go to the exam point',5,2,5000),500);
 assert.equal(m.travelHoldMs('Explore for Adventure Rank',3,2,5000),166);
 assert.equal(m.travelHoldMs('Explore for Adventure Rank',100,2,350),350);
 for(const objective of ['Talk to Amber','Talk to the informant','Investigate what Paimon has found'])assert.equal(m.travelHoldMs(objective,9,2,5000),null);
});
test('arrival, invalid data and exhausted deadlines cannot produce a movement hold',()=>{
 for(const [d,r,t] of [[2,2,1000],[1,2,1000],[10,2,0],[NaN,2,1000],[10,2,Infinity]])assert.equal(m.travelHoldMs('Go to the exam point',d,r,t),0);
});
test('conservative ordinary-ground simulation reduces near-waypoint observation stops without overshoot',()=>{
 function simulate(adaptive){let distance=9,holds=0;while(distance>2&&holds<100){const ms=adaptive?m.travelHoldMs('Go to the exam point',distance,2,10000):250;distance-=ms/1000*5;holds++;}return {distance,holds};}
 const old=simulate(false),updated=simulate(true);
 assert.ok(updated.holds<old.holds);assert.ok(updated.distance>=1.5);assert.ok(updated.distance<=2);
});
