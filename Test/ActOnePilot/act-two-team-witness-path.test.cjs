const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
test('team action loads a zero-padded retained witness before sending input',async()=>{
 const source=fs.readFileSync(process.env.BGI_MODULE||'BetterGenshinImpact/User/JsScript/ActOnePilot/bgi.js','utf8');
 const body=source.slice(source.indexOf('actTwoTeamUi: async function(){'),source.indexOf('actTwoHandbookRecoveryReady:function'));
 assert(body.startsWith('actTwoTeamUi: async function(){'));
 let saved=JSON.stringify({session:'test',frameId:385,witnessFrameId:378,action:'back'}),keys=[],reads=[];
 const context={request:{session:'test',expectedFrameId:385},lastObservation:{frameId:386},Date,events:[],checkStop(){},ready(){},
  file:{readTextSync(name){reads.push(name);if(name==='act-two-team.js')return 'var ActTwoTeam={target:()=>({key:"VK_ESCAPE",action:"back"})};';if(name==='act-two-team-request.json')return saved;if(name==='observations/test/frame-0378.json')return JSON.stringify({session:'test',frameId:378});return '';},writeTextSync(name,value){assert.equal(name,'act-two-team-request.json');saved=value;return true;}},
  boundedKey:async(key,ms,frame)=>keys.push({key,ms,frame}),actOneAccountUiClick:async()=>{throw Error('Unexpected click')},moveMouseTo(){},leftButtonDown(){},leftButtonUp(){},sleep:async()=>{}};
 vm.createContext(context);const api=vm.runInContext('({'+body+'})',context);
 assert.equal(await api.actTwoTeamUi(),'back');
 assert(reads.includes('observations/test/frame-0378.json'));
 assert.deepEqual(keys,[{key:'VK_ESCAPE',ms:60,frame:386}]);
});
