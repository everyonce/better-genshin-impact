const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const source=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js'),'utf8');
const body=source.split('}else if(ambushWitness){')[1].split('}else{Object.assign(result,await runChunk(current,0))')[0];
const AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
const run=new AsyncFunction('api',`const {runChunk,acquire,eligible,acquisition,checkStop,ready,moveMouseBy,sleep,observe,Date}=api;var current={},result={},events=[];${body};return {result,events};`);
function harness(options={}){
 let now=0,chunks=0,reads=0,moves=0;
 const api={Date:{now:()=>now},runChunk:async()=>{chunks++;now+=options.chunkMs||2200;return {nativeReturned:true,nativeMs:options.chunkMs||2200};},acquire:()=>({hud:{enemyBars:[{}]},valid:++reads!==(options.failAt||-1)}),eligible:o=>o.valid!==false,acquisition:{stationaryReady:()=>options.offCenter!==true,cameraDelta:()=>200},checkStop:()=>{},ready:()=>{},moveMouseBy:()=>moves++,sleep:async ms=>now+=ms,observe:async()=>({hud:{world:true}})};
 return {api,counts:()=>({chunks,reads,moves})};
}
test('actual native continuation is capped at three chunks without requiring bar association',async()=>{const h=harness(),out=await run(h.api);assert.equal(h.counts().chunks,3);assert.equal(out.result.nativeMs,6600);assert.equal(out.result.localChunks.length,3);});
test('fresh target or health rejection ends local continuation before another attack',async()=>{const h=harness({failAt:1}),out=await run(h.api);assert.equal(h.counts().chunks,1);assert.match(out.result.continuationStop,/changed/);});
test('unsuccessful local framing has two corrections and no extra attack',async()=>{const h=harness({offCenter:true});await run(h.api);assert.deepEqual(h.counts(),{chunks:1,reads:3,moves:2});});
test('local elapsed budget prevents a third long-running chunk',async()=>{const h=harness({chunkMs:5100});await run(h.api);assert.equal(h.counts().chunks,2);});
