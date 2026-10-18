// Test canonical publication candidates without replacing unrelated working-tree edits.
const Module=require('node:module'),path=require('node:path');
const root=path.resolve(__dirname,'../..'),resolve=Module._resolveFilename;
const targets=new Map(['bgi.js','act-two-field.js','mission.js'].map(name=>[
 path.join(root,'BetterGenshinImpact/User/JsScript/ActOnePilot',name).toLowerCase(),
 path.join(root,'artifacts/leyline-inspection',name)]));
Module._resolveFilename=function(request,parent,...rest){const result=resolve.call(this,request,parent,...rest);return typeof result==='string'?(targets.get(result.toLowerCase())||result):result;};
