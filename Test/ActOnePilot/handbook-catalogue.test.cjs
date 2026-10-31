'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../BetterGenshinImpact/User/JsScript/ActOnePilot');
const gate = require(path.join(root, 'handbook-catalogue.js'));
const engine = require(path.join(root, 'engine.js'));
const mission = require(path.join(root, 'mission.js'));
const clone = value => JSON.parse(JSON.stringify(value));
const row = (text, x, y, width = 120, height = 30) => ({text, x, y, width, height});

// This synthetic screen has the same bounded anchors as the retained run03 Easy screen.
function page() {
    return {session:'catalogue-test',frameId:2,timestamp:100000,capturedAt:99400,
        screenshotPath:'observations/catalogue-test/frame-0002.png',map:null,
        hud:{world:false,journal:false,bigMap:false,choice:false,dialogueReady:false,auto:false,
            climbing:false,groundControls:false,health:null,lowHealth:true},
        ocr:[row('Experience',232,232),row('Domains',233,329),row('Enemies',233,430),
            row('Guide',233,530,80),row('X',1654,218,39,39),row('Easy',402,189,67,38),
            row('Hilichurl Fighter',1043,262,310,37),row('Windrise, Mondstadt',1043,316,315,40),
            row('Navigate',1391,822,139,46)]};
}

// Every fixture request has a fresh frame newer than the frame explicitly acknowledged by its caller.
function request(step='handbookCatalogueScroll', patch={}) {
    return {id:'catalogue-1',session:'catalogue-test',expectedFrameId:1,createdAt:99000,mission:'questStep',step,...patch};
}

// Execute the complete adapter and engine while replacing only native IO and capture with inert fakes.
function harness(options={}) {
    let now=100000,foreground=true,windowsSession=3,scrolled=0,mapOpen=false,currentNative=null;
    const inputs=[],files=new Map(),writes=[],pins=[],context={};
    const adapterSource=fs.readFileSync(path.join(root,'bgi.js'),'utf8');
    const marker='        seedObservation: function (value) {';
    assert.equal(adapterSource.split(marker).length,2);
    // This test-only setter supplies the private native-capture result; production has no such API.
    const instrumented=adapterSource.replace(marker,
        '        __setTestCapture: function(value) { lastObservation=JSON.parse(JSON.stringify(value)); },\n'+marker);
    Object.assign(context,{
        Date:class extends Date { static now() { return now; } },
        file:{isExists:name=>files.has(name),readTextSync:name=>files.has(name)?files.get(name):fs.readFileSync(path.join(root,name),'utf8'),
            writeTextSync:(name,value)=>{files.set(name,value);writes.push(name);return true;}},
        genshin:{isRemoteDesktopSession:true,get windowsSessionId(){return windowsSession;},get isGameForeground(){return foreground;}},
        sleep:async milliseconds=>{now+=options.sleepMultiplier?milliseconds*options.sleepMultiplier:milliseconds;},
        moveMouseTo:(x,y)=>{
            inputs.push({kind:'move',x,y});
            if(options.loseFocusAfter==='move')foreground=false;
            if(options.changeSessionAfterMove)windowsSession=4;
            if(options.mutateSourceAfterMove){currentNative.ocr[0].text='Wrong menu';adapter.__setTestCapture(currentNative);}
            if(options.mutateRequestAfterMove)lastRequest.x=600;
        },
        verticalScroll:delta=>{
            inputs.push({kind:'scroll',delta});scrolled++;
            if(options.stopAfterScroll===scrolled)files.set('stop.json',JSON.stringify({session:'catalogue-test',createdAt:now}));
            if(options.throwScrollAt===scrolled)throw new Error('Synthetic scroll failure');
        },
        leftButtonDown:()=>{
            inputs.push({kind:'down'});
            if(options.loseFocusAfter==='down')foreground=false;
            if(options.stopAfterDown)files.set('stop.json',JSON.stringify({session:'catalogue-test',createdAt:now}));
            if(options.throwDown)throw new Error('Synthetic down failure');
        },
        leftButtonUp:()=>{inputs.push({kind:'up'});if(options.opensMap)mapOpen=true;},
        keyDown:()=>{throw new Error('Unexpected keyboard input');},keyUp:()=>{throw new Error('Unexpected keyboard release');}
    });
    vm.runInNewContext(instrumented,context);
    const adapter=context.createActOneAdapter(3);
    adapter.pinObservation=(session,frameId)=>{
        if(options.pinFailure&&frameId===2)throw new Error('Synthetic evidence pin failure');
        pins.push({session,frameId});
    };
    adapter.observe=async(session,frameId)=>{
        const capturedAt=now;now+=600;
        currentNative=page();Object.assign(currentNative,{session,frameId,capturedAt,timestamp:now,
            screenshotPath:'observations/'+session+'/frame-'+String(frameId).padStart(4,'0')+'.png'});
        if(mapOpen){currentNative.hud.bigMap=true;currentNative.ocr=[];}
        if(options.observationMutation)options.observationMutation(currentNative,now);
        adapter.__setTestCapture(currentNative);
        return clone(currentNative);
    };
    adapter.actTwoHandbookClaim=async()=>{throw new Error('Catalogue fell through to reward claim');};
    const runner=engine.create(adapter,{session:'catalogue-test',enableInput:options.enableInput!==false});
    let lastRequest=null;
    return {adapter,runner,inputs,writes,pins,files,context,
        events:()=>clone(adapter.events()),
        catalogueEvent:()=>clone(adapter.events().find(event=>event.type==='handbookCatalogueCommand')||null),
        native:()=>clone(currentNative),
        async run(step,patch={}) {
            if(!runner.getFrame())await runner.observe();
            lastRequest=request(step,{createdAt:now,expectedFrameId:runner.getFrame(),...patch});
            try { return await runner.process(lastRequest,()=>mission); }
            catch(error) {
                // The engine deliberately throws after preserving its failed terminal receipt.
                assert.equal(JSON.parse(files.get('receipt.json')).status,'failed');
                return 'failed';
            }
        },
        async replay() { return runner.process(lastRequest,()=>mission); },
        receipt:()=>JSON.parse(files.get('receipt.json'))
    };
}

test('pure catalogue gate admits only its fixed scroll, interior icon and exact Mondstadt enemy target',()=>{
    assert.deepEqual(gate.target(page(),100000,request()),
        {command:'handbookCatalogueScroll',action:'scrollCatalogue',x:680,y:670,ticks:8,delta:-1});
    assert.equal(gate.target(page(),100000,request('handbookCatalogueSelect',{x:421,y:869})).action,'selectCatalogueIcon');
    const target=gate.target(page(),100000,request('handbookCatalogueTrack',{enemyName:'Hilichurl Fighter'}));
    assert.equal(target.enemyName,'Hilichurl Fighter');assert.equal(target.location,'Windrise, Mondstadt');
    assert.deepEqual([target.x,target.y],[1461,845]);
});

test('a two-line selected title must match the entire explicit name',()=>{
    const value=page();value.ocr=value.ocr.filter(item=>item.text!=='Hilichurl Fighter');
    value.ocr.find(item=>item.text==='Windrise, Mondstadt').y=350;
    value.ocr.push(row('Wooden Shield',1043,254,280,30),row('Hilichurl Guard',1043,292,280,30));
    assert(gate.target(value,100000,request('handbookCatalogueTrack',{enemyName:'Wooden Shield Hilichurl Guard'})));
    assert.equal(gate.target(value,100000,request('handbookCatalogueTrack',{enemyName:'Hilichurl Guard'})),null);
});

// Exact rows retained in camp-handbook-pilot-08/before-handbook.json; raw OCR remains unchanged.
function run08Rows(value) {
    Object.assign(value.ocr.find(item=>item.text==='Hilichurl Fighter'),
        {text:'Slime',x:1040,y:258,width:105,height:43});
    Object.assign(value.ocr.find(item=>item.text==='Windrise, Mondstadt'),
        {text:'OStormbearer Mountains,Mondstadt',x:1046,y:320,width:413,height:26});
}

test('run08 location accepts comma whitespace while preserving its leading O and the exact Slime title',()=>{
    const req=request('handbookCatalogueTrack',{enemyName:'Slime'});
    for(const spelling of ['OStormbearer Mountains,Mondstadt','OStormbearer Mountains, Mondstadt',
        'OStormbearer Mountains ,  Mondstadt']){
        const value=page();run08Rows(value);value.ocr.find(item=>item.x===1046).text=spelling;
        const target=gate.target(value,100000,req);
        assert.equal(target.location,'OStormbearer Mountains, Mondstadt');assert.deepEqual(target.title,['Slime']);
        assert.equal(value.ocr.find(item=>item.x===1046).text,spelling);
        assert.equal(gate.target(value,100000,{...req,enemyName:'Large Slime'}),null);
    }
});

test('location normalization cannot hide a wrong region, arbitrary glyph, title mismatch or duplicate location',()=>{
    const req=request('handbookCatalogueTrack',{enemyName:'Slime'});
    for(const spelling of ['OStormbearer Mountains,Liyue','OStormbearer Mountains,Mondstadt Extra',
        'OStormbearer Mountains,mondstadt','@Stormbearer Mountains,Mondstadt','○Stormbearer Mountains,Mondstadt']){
        const value=page();run08Rows(value);value.ocr.find(item=>item.x===1046).text=spelling;
        assert.equal(gate.target(value,100000,req),null,spelling);
    }
    const wrongTitle=page();run08Rows(wrongTitle);wrongTitle.ocr.find(item=>item.text==='Slime').text='O Slime';
    assert.equal(gate.target(wrongTitle,100000,req),null);
    const duplicate=page();run08Rows(duplicate);
    duplicate.ocr.push({...duplicate.ocr.find(item=>item.x===1046),text:'OStormbearer Mountains, Mondstadt'});
    assert.equal(gate.target(duplicate,100000,req),null);
});

test('real engine and adapter track the run08 Slime once without changing raw source OCR',async()=>{
    const f=harness({opensMap:true,observationMutation:value=>{if(!value.hud.bigMap)run08Rows(value);}});
    assert.equal(await f.run('handbookCatalogueTrack',{enemyName:'Slime'}),'completed');
    assert.deepEqual(f.inputs,[{kind:'move',x:1461,y:845},{kind:'down'},{kind:'up'}]);
    assert.equal(f.catalogueEvent().target.location,'OStormbearer Mountains, Mondstadt');
    const retained=JSON.parse(f.files.get('observations/catalogue-test/frame-0002.json'));
    assert(retained.ocr.some(item=>item.text==='OStormbearer Mountains,Mondstadt'));
    assert.equal(f.receipt().details.result.mapOpened,true);assert.equal(f.catalogueEvent().clicks,1);
});

test('wrong menu, session, frame, future or stale observation and stale capture cannot authorize any command',()=>{
    const mutations=[value=>{value.session='other';},value=>{value.frameId=1;},value=>{value.timestamp=100001;},
        value=>{value.timestamp=98999;},value=>{value.capturedAt=97999;},value=>{delete value.capturedAt;},
        value=>{value.capturedAt=100001;},value=>{value.map={x:1,y:2};},
        value=>{value.ocr.find(item=>item.text==='Easy').text='All';}];
    for(const key of ['world','journal','bigMap','choice','dialogueReady','auto','climbing','groundControls']){
        mutations.push(value=>{value.hud[key]=true;});mutations.push(value=>{delete value.hud[key];});
    }
    for(const mutate of mutations){const value=page();mutate(value);assert.equal(gate.target(value,100000,request()),null);}
    assert.equal(gate.target(page(),101001,request()),null);
    assert.equal(gate.target(page(),NaN,request()),null);
    const boundary=page();Object.assign(boundary,{capturedAt:98000,timestamp:99000});
    assert(gate.target(boundary,100000,request('handbookCatalogueScroll',{createdAt:97000})));
    boundary.capturedAt--;
    assert.equal(gate.target(boundary,100000,request('handbookCatalogueScroll',{createdAt:97000})),null);
});

test('every handbook anchor must be present, uniquely located and bounded; an open category popup is refused',()=>{
    for(const name of ['Experience','Domains','Enemies','Guide','X','Easy']){
        const missing=page();missing.ocr=missing.ocr.filter(item=>item.text!==name);
        assert.equal(gate.target(missing,100000,request()),null,name);
        const duplicate=page();duplicate.ocr.push({...duplicate.ocr.find(item=>item.text===name)});
        assert.equal(gate.target(duplicate,100000,request()),null,name);
        const moved=page();moved.ocr.find(item=>item.text===name).x+=300;
        assert.equal(gate.target(moved,100000,request()),null,name);
        const oversized=page();oversized.ocr.find(item=>item.text===name).width=2000;
        assert.equal(gate.target(oversized,100000,request()),null,name);
    }
    const popup=page();popup.ocr.push(row('Boss Enemies',402,407,170));
    assert.equal(gate.target(popup,100000,request()),null);
});

test('track refuses another enemy or region, ambiguous title/location/button and misplaced body text',()=>{
    const req=request('handbookCatalogueTrack',{enemyName:'Hilichurl Fighter'});
    for(const mutate of [value=>{value.ocr.find(item=>item.text==='Hilichurl Fighter').text='Hilichurl Shooter';},
        value=>{value.ocr.find(item=>item.text==='Windrise, Mondstadt').text='Fellfrost Peak, Snezhnaya';},
        value=>{value.ocr.find(item=>item.text==='Hilichurl Fighter').y=410;},
        value=>{value.ocr.find(item=>item.text==='Navigate').x=1200;}]){
        const value=page();mutate(value);assert.equal(gate.target(value,100000,req),null);
    }
    for(const name of ['Hilichurl Fighter','Windrise, Mondstadt','Navigate']){
        const value=page();value.ocr.push({...value.ocr.find(item=>item.text===name)});
        assert.equal(gate.target(value,100000,req),null,name);
        value.ocr=value.ocr.filter(item=>item.text!==name);
        assert.equal(gate.target(value,100000,req),null,name);
    }
});

test('real engine and adapter emit exactly eight downward ticks, preserve provenance and reject replay',async()=>{
    const f=harness();assert.equal(await f.run('handbookCatalogueScroll'),'completed');
    assert.deepEqual(f.inputs,[{kind:'move',x:680,y:670},...Array.from({length:8},()=>({kind:'scroll',delta:-1}))]);
    const event=f.catalogueEvent();assert.equal(event.status,'completed');assert.equal(event.scrollTicks,8);
    assert.equal(event.scrollAttempts,8);assert.equal(event.clicks,0);assert.equal(event.inputs.length,9);
    assert.equal(event.sourceFrame.frameId,2);assert(event.sourceFrame.capturedAt<event.sourceFrame.timestamp);
    assert.equal(event.finishedAt-event.startedAt,800);assert.equal(event.sourceClock.kind,'Date.now');
    assert(event.inputs.every(item=>item.dispatched&&item.returned&&item.readinessPassed&&item.observationAgeMs<=1000&&item.captureAgeMs<=2000));
    assert.equal(event.sourcePinned,true);assert(f.pins.some(value=>value.session==='catalogue-test'&&value.frameId===2));
    assert(f.events().find(item=>item.type==='controllerRevision').files['handbook-catalogue.js']);
    assert.equal(await f.replay(),'rejected');assert.equal(f.inputs.length,9);
    await assert.rejects(f.adapter.handbookCatalogue('handbookCatalogueScroll',f.native()),/Unused explicit/);
    assert(!f.writes.includes('act-two-handbook-claim.json'));
});

test('real engine selects one interior icon without tracking, reward claiming or further input',async()=>{
    const f=harness();assert.equal(await f.run('handbookCatalogueSelect',{x:700,y:560}),'completed');
    assert.deepEqual(f.inputs,[{kind:'move',x:700,y:560},{kind:'down'},{kind:'up'}]);
    const event=f.catalogueEvent();assert.equal(event.clicks,1);assert.equal(event.scrollTicks,0);
    assert.equal(event.target.action,'selectCatalogueIcon');assert.equal(event.claimAttempted,false);
    assert.equal(f.receipt().details.result.claimAttempted,false);assert(!f.writes.includes('act-two-handbook-claim.json'));
});

test('real named track returns the opened map normally without closing it or starting navigation',async()=>{
    const f=harness({opensMap:true});assert.equal(await f.run('handbookCatalogueTrack',{enemyName:'Hilichurl Fighter'}),'completed');
    assert.deepEqual(f.inputs,[{kind:'move',x:1461,y:845},{kind:'down'},{kind:'up'}]);
    assert.equal(f.receipt().details.result.mapOpened,true);assert.equal(f.receipt().details.result.claimAttempted,false);
    assert.equal(f.catalogueEvent().target.enemyName,'Hilichurl Fighter');assert.equal(f.catalogueEvent().clicks,1);
});

test('real engine rejects strict schema violations before native input',async()=>{
    const cases=[['handbookCatalogueScroll',{x:500}],['handbookCatalogueScroll',{ticks:80}],
        ['handbookCatalogueSelect',{x:420,y:500}],['handbookCatalogueSelect',{x:940,y:500}],
        ['handbookCatalogueSelect',{x:500,y:265}],['handbookCatalogueSelect',{x:500,y:870}],
        ['handbookCatalogueSelect',{x:500.1,y:500}],['handbookCatalogueSelect',{x:'500',y:500}],
        ['handbookCatalogueSelect',{x:1400,y:830}],['handbookCatalogueSelect',{x:500,y:500,enemyName:'Slime'}],
        ['handbookCatalogueTrack',{}],['handbookCatalogueTrack',{enemyName:' Hilichurl Fighter'}],
        ['handbookCatalogueTrack',{enemyName:'Hilichurl  Fighter'}],['handbookCatalogueTrack',{enemyName:'Slime',x:1400}],
        ['actTwoHandbookClaim',{x:500,y:500}],['handbookCatalogueScroll',{code:'leftButtonDown()'}]];
    for(const [step,patch] of cases){const f=harness();assert.equal(await f.run(step,patch),'rejected');assert.equal(f.inputs.length,0);}
});

test('real adapter independently rejects invalid schemas and nonmatching engine/native frames',async()=>{
    const f=harness();const invalid=request('handbookCatalogueSelect',{x:1400,y:830});
    f.adapter.beginMission(invalid);
    await assert.rejects(f.adapter.handbookCatalogue(invalid.step,page()),/Unused explicit/);
    assert.equal(f.inputs.length,0);
    const mismatch=harness({observationMutation:value=>{value.session='different-native-session';}});
    assert.equal(await mismatch.run('handbookCatalogueScroll'),'failed');assert.equal(mismatch.inputs.length,0);
});

test('freshness, incorrect enemy/region and input-disabled failures cannot fall through to legacy claim handling',async()=>{
    for(const options of [{enableInput:false},
        {observationMutation:value=>{value.capturedAt-=3000;}},
        {observationMutation:value=>{value.ocr.find(item=>item.text==='Easy').text='All';}},
        {observationMutation:value=>{value.ocr.find(item=>item.text==='Windrise, Mondstadt').text='Mt. Aocang, Liyue';}}]){
        const f=harness(options);assert.equal(await f.run('handbookCatalogueTrack',{enemyName:'Hilichurl Fighter'}),'failed');
        assert.equal(f.inputs.length,0);assert(!f.writes.includes('act-two-handbook-claim.json'));
    }
    const wrong=harness();assert.equal(await wrong.run('handbookCatalogueTrack',{enemyName:'Hilichurl Shooter'}),'failed');
    assert.equal(wrong.inputs.length,0);
});

test('source evidence must be pinned before the first physical event',async()=>{
    const f=harness({pinFailure:true});assert.equal(await f.run('handbookCatalogueScroll'),'failed');
    assert.equal(f.inputs.length,0);assert.equal(f.catalogueEvent().sourcePinned,false);
    assert.match(f.catalogueEvent().error,/evidence pin failure/);
    assert.match(f.receipt().details.capturePinError,/evidence pin failure/);
});

test('focus, RDP identity, mutable request and mutable source are checked again before the click',async()=>{
    for(const options of [{loseFocusAfter:'move'},{changeSessionAfterMove:true},{mutateRequestAfterMove:true},{mutateSourceAfterMove:true}]){
        const f=harness(options);assert.equal(await f.run('handbookCatalogueSelect',{x:700,y:560}),'failed');
        assert.deepEqual(f.inputs,[{kind:'move',x:700,y:560}]);assert.equal(f.catalogueEvent().clickAttempts,0);
    }
});

test('an attempted down always receives one cleanup release, with focus/STOP/native errors retained',async()=>{
    for(const options of [{loseFocusAfter:'down'},{stopAfterDown:true},{throwDown:true}]){
        const f=harness(options);assert.equal(await f.run('handbookCatalogueSelect',{x:700,y:560}),'failed');
        assert.deepEqual(f.inputs,[{kind:'move',x:700,y:560},{kind:'down'},{kind:'up'}]);
        const event=f.catalogueEvent();assert.equal(event.status,'failed');assert(event.error);assert.equal(event.buttonUpAttempts,1);
        assert.equal(event.inputs.at(-1).cleanup,true);assert.equal(event.inputs.at(-1).returned,true);
    }
});

test('scroll STOP, lost freshness and native errors stop the finite operation without retry',async()=>{
    for(const options of [{stopAfterScroll:3},{sleepMultiplier:5},{throwScrollAt:2}]){
        const f=harness(options);assert.equal(await f.run('handbookCatalogueScroll'),'failed');
        const event=f.catalogueEvent();assert(event.scrollAttempts>0&&event.scrollAttempts<8);assert.equal(event.status,'failed');
        assert.equal(event.scrollAttempts,options.throwScrollAt?2:3);assert.equal(event.scrollTicks,options.throwScrollAt?1:3);
        assert.equal(event.clickAttempts,0);assert(event.finishedAt>=event.startedAt);
        assert.equal(await f.replay(),'rejected');
    }
});
