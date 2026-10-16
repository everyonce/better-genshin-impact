var ActTwoJournalRecovery = (function () {
    function ready(o, now, session, originalAccount) {
        var h=o&&o.hud;
        if(!o||o.session!==session||!Number.isInteger(o.frameId)||!Number.isFinite(o.timestamp)||now<o.timestamp||now-o.timestamp>1000||
           !originalAccount||o.map!==null||!h||h.journal!==true||h.world!==false||h.health||h.groundControls||h.bigMap||h.auto||h.dialogueReady||h.choice||!Array.isArray(o.ocr))return false;
        function one(text,x0,x1,y0,y1){return o.ocr.filter(function(r){return String(r.text||'').trim()===text&&r.x>=x0&&r.x<=x1&&r.y>=y0&&r.y<=y1;}).length===1;}
        return one('In Progress',100,350,15,80)&&one('Not to be Missed',850,1200,100,160)&&
            one('Defeat the attacking monsters',850,1350,230,290)&&one('Quest Chain Rewards:',850,1200,760,820)&&
            one('World Quests',130,400,100,900)&&one('Cancel',1550,1770,970,1020)&&one('Navigation',1500,1800,1000,1060);
    }
    return {ready:ready};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=ActTwoJournalRecovery;
