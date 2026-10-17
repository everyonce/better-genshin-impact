(function(root){
    'use strict';
    var quests=["Welcome to the Adventurers' Guild","Kaeya's Troubles",'Mystery of the Arcadian Ruins','Shadow Over Mondstadt',"Sharpening the Axe Won't Hinder the Work",'The Art of Cooking','The Blessings of The Seven','Scent on the Wind','Glide With the Wind','License to Glide','Outrider Style','Collector of Anemo Sigils','Not to be Missed'];
    function target(o,now,plan,request) {
        if(!o||!o.hud||(o.hud.journal!==true&&!(plan&&plan.action==='returnAllQuests'&&plan.quest==='Collector of Anemo Sigils'))||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||
            !plan||plan.reviewed!==true||plan.consumed===true||!request||plan.session!==request.session||plan.frameId!==request.expectedFrameId||
            !Number.isFinite(plan.createdAt)||now<plan.createdAt||now-plan.createdAt>60000||quests.indexOf(plan.quest)<0)return null;
        var rows=o.ocr||[];
        function unique(text,x0,x1,y0,y1){var found=rows.filter(function(r){return String(r.text||'').trim()===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1;});return found.length===1?found[0]:null;}
        if(plan.action==='returnAllQuests'&&plan.quest==='Collector of Anemo Sigils'&&unique('World Quests',120,350,15,80)&&(unique('World Quests',150,400,90,160)||unique('\uff01World Quests',150,400,90,160))&&unique('Collector of Anemo Sigils',120,700,160,240)&&unique('Collector of Anemo Sigils',850,1350,90,180)&&unique('Q',650,700,20,65)&&unique('E',1200,1250,20,65))return {x:768,y:48};
        if(!unique('In Progress',100,350,15,80)||!(unique('Archon Quests',80,450,90,160)||unique('World Quests',150,400,90,860)||plan.quest==='Outrider Style'&&unique('Story Quests',150,400,140,180)&&unique('Outrider Style',850,1300,90,180)&&unique("Enter Raptor's Hideout",900,1300,230,290)))return null;
        if(plan.action==='inspectWorldQuestTab'&&plan.quest==='Shadow Over Mondstadt'&&unique('Archon Quests',80,450,90,160)&&unique('Shadow Over Mondstadt',120,700,250,350)&&unique('License to Glide',120,700,500,620)&&unique('Mystery of the Arcadian Ruins',120,700,680,820)&&unique('Q',650,700,20,65)&&unique('E',1200,1250,20,65))return {x:1152,y:48};
        if(plan.action==='scrollToCyrus'&&plan.quest==='Not to be Missed'&&unique('World Quests',150,400,650,860)&&unique('Collector of Anemo Sigils',120,700,800,970)&&!unique(plan.quest,120,700,160,970))return {x:500,y:800,scroll:-2};
        var row;
        if(plan.action==='select')row=unique(plan.quest,120,700,160,970);
        else if(plan.action==='navigate'&&unique(plan.quest,850,1300,90,180))row=unique('Navigate',1450,1800,880,1040);
        var trackedObjective=plan.quest==='License to Glide'&&unique('Go to the exam point',900,1300,230,290)||plan.quest==='Mystery of the Arcadian Ruins'&&unique('Solve the mystery (Go to Kaeya at the Knights of Favonius HQ for a',900,1300,230,290)&&unique('hint)',900,1000,265,310);
        if(plan.action==='cancelNavigation'&&unique(plan.quest,850,1300,90,180)&&trackedObjective){var cancel=unique('Cancel',1600,1650,980,1005),nav=unique('Navigation',1580,1620,1006,1035);if(cancel&&nav)row={x:1597,y:989,width:151,height:60};}
        if(!row||!Number.isFinite(row.width)||!Number.isFinite(row.height)||row.width<=0||row.height<=0)return null;
        return {x:Math.round(row.x+row.width/2),y:Math.round(row.y+row.height/2)};
    }
    root.ActTwoJournal={target:target};
    if(typeof module!=='undefined'&&module.exports)module.exports=root.ActTwoJournal;
})(typeof globalThis!=='undefined'?globalThis:this);
