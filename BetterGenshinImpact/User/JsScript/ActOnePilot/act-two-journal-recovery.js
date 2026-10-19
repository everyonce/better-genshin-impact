var ActTwoJournalRecovery = (function () {
    function ready(o, now, session, originalAccount) {
        var h=o&&o.hud;
        if(!o||o.session!==session||!Number.isInteger(o.frameId)||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||
           !originalAccount||o.map!==null||!h||h.world!==false||h.health||h.groundControls||h.bigMap||h.auto||h.dialogueReady||h.choice||!Array.isArray(o.ocr))return false;
        function one(text,x0,x1,y0,y1){return o.ocr.filter(function(r){return String(r.text||'').trim()===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1;}).length===1;}
        if(one('World Quests',100,350,15,80)&&one('No active quests',650,1300,430,540)&&one('Check another tab',750,1150,540,630)&&one('Q',650,700,20,65)&&one('E',1200,1250,20,65))return true;
        if(h.journal===true&&one('In Progress',130,160,20,45)&&one('For a Tomorrow Without Tears',145,165,135,155)&&one('Shadow Over Mondstadt',185,210,230,255)&&one('Requires Adventure Rank 10',185,210,260,280)&&one('Outrider Style',855,885,105,130)&&one("Enter Raptor's Hideout",910,940,245,270)&&one('Cancel',1600,1640,980,1005)&&one('Navigation',1580,1610,1005,1030))return true;
        return h.journal===true&&one('In Progress',100,350,15,80)&&one('Not to be Missed',850,1200,100,160)&&
            one('Defeat the attacking monsters',850,1350,230,290)&&one('Quest Chain Rewards:',850,1200,760,820)&&
            one('World Quests',130,400,100,900)&&one('Cancel',1550,1770,970,1020)&&one('Navigation',1500,1800,1000,1060);
    }
    return {ready:ready};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=ActTwoJournalRecovery;
