(function(root){
    'use strict';
    var quests=["Welcome to the Adventurers' Guild","Kaeya's Troubles",'Mystery of the Arcadian Ruins','Shadow Over Mondstadt',"Sharpening the Axe Won't Hinder the Work"];
    function target(o,now,plan,request) {
        if(!o||!o.hud||o.hud.journal!==true||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||
            !plan||plan.reviewed!==true||plan.consumed===true||!request||plan.session!==request.session||plan.frameId!==request.expectedFrameId||
            !Number.isFinite(plan.createdAt)||now<plan.createdAt||now-plan.createdAt>60000||quests.indexOf(plan.quest)<0)return null;
        var rows=o.ocr||[];
        function unique(text,x0,x1,y0,y1){var found=rows.filter(function(r){return String(r.text||'').trim()===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1;});return found.length===1?found[0]:null;}
        if(!unique('In Progress',100,350,15,80)||!unique('Archon Quests',80,450,90,160))return null;
        var row;
        if(plan.action==='select')row=unique(plan.quest,120,700,160,970);
        else if(plan.action==='navigate'&&unique(plan.quest,850,1300,90,180))row=unique('Navigate',1450,1800,880,1040);
        if(!row||!Number.isFinite(row.width)||!Number.isFinite(row.height)||row.width<=0||row.height<=0)return null;
        return {x:Math.round(row.x+row.width/2),y:Math.round(row.y+row.height/2)};
    }
    root.ActTwoJournal={target:target};
    if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoJournal;
})(typeof globalThis!=='undefined'?globalThis:this);
