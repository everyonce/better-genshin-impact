const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
test('close Cyrus recipe keeps position and turns by attacking before skill',()=>{
 const line=fs.readFileSync(require.resolve('../../BetterGenshinImpact/User/AutoFight/English Cyrus Defense.txt'),'utf8').split('\n').find(l=>!l.startsWith('//')&&l.trim());
 assert.ok(line.startsWith('\u51ef\u4e9a '));
 const held=new Set(),commands=line.slice(line.indexOf(' ')+1).split(',').map(x=>x.trim());
 let forwardMs=0;
 for(const command of commands){const [,kind,arg]=/^(\w+)\(([^)]*)\)$/.exec(command);
  assert.ok(['keydown','keyup','keypress','wait','click'].includes(kind));
  if(kind==='keydown'){assert.fail('No held movement in the camp rock encounter');}
  if(kind==='wait'){assert.ok(Number(arg)<=.2);if(held.has('w'))forwardMs+=Number(arg)*1000;}
  if(kind==='keyup')assert.equal(held.delete(arg),true);
  if(kind==='keypress')assert.equal(held.size,0);
 }
 assert.equal(forwardMs,0);assert.equal(held.size,0);
 assert.ok(commands.indexOf('click(left)')<commands.indexOf('keypress(e)'));
 assert.equal(commands.includes('click(right)'),false);
});
