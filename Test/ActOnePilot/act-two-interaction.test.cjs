const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const interaction=require('../../BetterGenshinImpact/User/JsScript/ActOnePilot/act-two-interaction.js');
const fixture=JSON.parse(fs.readFileSync(__dirname+'/act-two-wood-selection.fixture.json','utf8'));
test('real Wood-first list cannot authorize Kaeya F without selecting the next row',()=>{
 assert.equal(interaction.selection(fixture.ocr,'Kaeya'),'next');
 assert.equal(interaction.selection(fixture.ocr,'Wood'),'selected');
 const rows=fixture.ocr.filter(r=>r.text!=='F').concat({text:'F',x:1107,y:560,width:24,height:28});
 assert.equal(interaction.selection(rows,'Kaeya'),'selected');
 assert.equal(interaction.selection(rows,'Wood'),null);
 assert.equal(interaction.selection(rows.concat({text:'Kaeya',x:1200,y:570,height:30}),'Kaeya'),null);
 assert.equal(interaction.selection([{text:'Kaeya',x:1664,y:441,height:36},{text:'F',x:1107,y:440,height:28}],'Kaeya'),null);
});
