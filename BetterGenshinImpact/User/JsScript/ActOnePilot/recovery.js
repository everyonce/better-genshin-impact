var ActOneRecovery = (function () {
    var climbObjectives=['Go to the location designated by Amber','Go to the Knights of Favonius Headquarters','Talk to Amber','Meet Kaeya at the temple','Meet Lisa at the temple'];
    function hasClimbObjective(current) {
        return !!(current&&current.hud&&Array.isArray(current.hud.objectives)&&current.hud.objectives.some(function(s){
            var normalized=String(s).replace(/\s+/g,'');
            return climbObjectives.some(function(allowed){return normalized===allowed.replace(/\s+/g,'');});
        }));
    }
    function safeClimbingWorld(current) {
        var h=current&&current.hud,hp=h&&h.health;
        return !!(h&&h.world===true&&h.climbing===true&&!h.journal&&!h.bigMap&&!h.tutorialStep&&
            !h.dialogueReady&&!h.choice&&!h.objectiveChanged&&!h.lowHealth&&
            hasClimbObjective(current)&&
            hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current>=0&&
            hp.current<=hp.max&&hp.current/hp.max>=0.6);
    }
    function safeDescentWorld(current) {
        var h=current&&current.hud,hp=h&&h.health;
        return !!(h&&h.world===true&&!h.journal&&!h.bigMap&&!h.tutorialStep&&
            !h.dialogueReady&&!h.choice&&!h.objectiveChanged&&!h.lowHealth&&
            hasClimbObjective(current)&&hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&
            hp.max>0&&hp.current>=0&&hp.current<=hp.max&&hp.current/hp.max>=0.6);
    }
    function hasGroundControls(current) {
        if(current&&current.hud&&current.hud.groundControls===true) return true;
        var controls=(current.ocr||[]).filter(function(r){return /^(E|Q|Space)$/.test(String(r.text||'').trim())&&r.x>1500&&r.x<1880&&r.y>=990&&r.y<=1045;});
        return controls.some(function(r){return /^(E|Q)$/.test(String(r.text||'').trim());})&&
            !controls.some(function(r){return String(r.text||'').trim()==='Space';});
    }
    function safeStatueInteraction(current, now, fPrompt) {
        var h=current&&current.hud,rows=current&&current.ocr||[];
        if(!current||!Number.isFinite(current.timestamp)||!Number.isFinite(now)||now<current.timestamp||now-current.timestamp>1000||
            !current.map||current.map.map!=='Teyvat'||!Number.isFinite(current.map.x)||!Number.isFinite(current.map.y)||
            Math.hypot(current.map.x+1323.474,current.map.y-2566.115)>3||!h||h.world!==false||h.groundControls!==true||h.climbing!==false||
            h.journal!==false||h.bigMap!==false||h.dialogueReady!==false||h.choice!==false||h.auto!==false||
            h.objectiveChanged!==false||h.tutorialStep!==null||!Array.isArray(h.enemyBars)||h.enemyBars.length!==0) return false;
        var statues=rows.filter(function(r){return String(r.text||'').trim()==='Statue of The Seven';});
        if(statues.length!==1) return false;
        var s=statues[0],sx=Number(s.x),sy=Number(s.y),sw=Number(s.width),sh=Number(s.height);
        if(!Number.isFinite(sx)||!Number.isFinite(sy)||!Number.isFinite(sw)||!Number.isFinite(sh)||
            sx<1150||sx>1280||sy<490||sy>555||sw<240||sw>310||sh<20||sh>40) return false;
        var fRows=rows.filter(function(r){return String(r.text||'').trim()==='F'&&Number(r.x)>=1080&&Number(r.x)<=1170&&Number(r.y)>=490&&Number(r.y)<=590;});
        if(fRows.length>1) return false;
        if(fRows.length===1) return true;
        return !!(fPrompt&&fPrompt.frameId===current.frameId&&String(fPrompt.text||'').trim()==='F'&&Number(fPrompt.x)>=1080&&Number(fPrompt.x)<=1170&&
            Number(fPrompt.y)>=490&&Number(fPrompt.y)<=590);
    }
    function hasStatueHealingPanel(current) {
        var rows=current&&current.ocr||[];
        return rows.some(function(r){return /Click on the character portrait to restore HP/.test(String(r.text||''))&&Number(r.y)<100;})&&
            rows.some(function(r){return /^Statue.s Blessing$/.test(String(r.text||'').trim())&&Number(r.x)>1400&&Number(r.y)<100;})&&
            rows.some(function(r){return /Restorative Power:\s*[1-9][0-9]*\s*\//.test(String(r.text||''));});
    }
    async function openUnknownHealthStatue(current,api,observe,depth) {
        var hp=current&&current.hud&&current.hud.health;
        if(hp&&Number.isFinite(hp.current)&&Number.isFinite(hp.max)&&hp.max>0&&hp.current>=0&&hp.current<=hp.max) return null;
        var now=typeof api.now==='function'?api.now():NaN;
        var fPrompt=(current&&current.ocr||[]).filter(function(r){return String(r.text||'').trim()==='F'&&Number(r.x)>=1080&&Number(r.x)<=1170&&Number(r.y)>=490&&Number(r.y)<=590;})[0]||null;
        if(!fPrompt&&typeof api.statueInteractionF==='function') fPrompt=await api.statueInteractionF(current);
        if(!safeStatueInteraction(current,now,fPrompt)) return null;
        api.checkStop();await api.keyPress('VK_F');await api.sleep(700);current=await observe();
        for(var speakerPoll=0;speakerPoll<3&&!(current.ocr||[]).some(function(r){return String(r.text||'').trim()==='Statue of The Seven'&&Number(r.y)>830&&Number(r.y)<910;});speakerPoll++) {
            api.checkStop();await api.sleep(250);current=await observe();
        }
        if((current.ocr||[]).some(function(r){return String(r.text||'').trim()==='Statue of The Seven'&&Number(r.y)>830&&Number(r.y)<910;}))
            return await run(current,api,observe,depth+1);
        return {status:'stopped',reason:'Statue interaction sent once; fresh speaker state not confirmed'};
    }
    async function descendClimb(current,api,observe) {
        if(!safeClimbingWorld(current)) return null;
        var initialHealth=current.hud.health,steps=0,groundedFrames=0,groundedChecks=0;
        while(true) {
            api.checkStop();
            if(!safeDescentWorld(current)) return {status:'stopped',reason:'Unsafe or changed state during bounded climb descent',climbSteps:steps};
            if(initialHealth.current-current.hud.health.current>initialHealth.max*0.1)
                return {status:'stopped',reason:'Health dropped more than 10% during bounded climb descent',climbSteps:steps};
            if(current.hud.climbing) {
                if(steps>=12) return {status:'stopped',reason:'Bounded climb descent hold limit reached',climbSteps:steps};
                await api.descendClimb(800);steps++;groundedFrames=0;await api.sleep(200);current=await observe();
                continue;
            }
            if(safeGroundedWorld(current,initialHealth)&&hasGroundControls(current)) groundedFrames++;
            else groundedFrames=0;
            if(groundedFrames>=3) return {status:'completed',reason:'Climb descent reached world ground',climbSteps:steps};
            if(groundedChecks>=3) return {status:'stopped',reason:'Grounded HUD controls not confirmed',climbSteps:steps};
            // Climbing OCR can miss the X prompt for one frame. Wait and
            // reobserve without input; if climbing returns the bounded descent resumes.
            await api.sleep(200);current=await observe();groundedChecks++;
        }
    }
    function safeGroundedWorld(current,initialHealth) {
        var h=current&&current.hud,hp=h&&h.health;
        return !!(safeDescentWorld(current)&&h.climbing===false&&hp&&
            initialHealth.current-hp.current<=initialHealth.max*0.1);
    }
    async function run(current, api, observe, depth) {
        depth=depth||0;
        if(depth>4) return {status:'stopped',reason:'Recovery transition limit reached'};
        // Check both the initial frame and later observations: health OCR may
        // alternate between valid and collapsed slash-formatted values.
        var unknownStatue=await openUnknownHealthStatue(current,api,observe,depth);
        if(unknownStatue) return unknownStatue;
        if(typeof api.wolfInfoReady==='function'&&api.wolfInfoReady(current)) {
            api.checkStop();api.recoverWolfInfo();await api.sleep(500);var wolfInfoNext=await observe();
            return {status:'completed',reason:'One verified Wolf tutorial slide dismissed; inspect the fresh next screen',clicks:1,frameId:wolfInfoNext&&wolfInfoNext.frameId};
        }
        if(current&&current.hud&&current.hud.climbing===true&&hasClimbObjective(current)) {
            if(!safeClimbingWorld(current)) return {status:'stopped',reason:'Unsafe initial state for bounded climb descent',climbSteps:0};
            var descent=await descendClimb(current,api,observe);
            if(descent) return descent;
        }
        if(hasStatueHealingPanel(current)) {
            // The Statue restores one tenth of max HP per portrait click.
            // Passive recovery has already restored at least half; cap at five clicks.
            for(var healClick=0;healClick<5;healClick++) {
                api.checkStop();await api.healTravelerAtStatue();await api.sleep(700);current=await observe();
                for(var panelPoll=0;panelPoll<3&&!hasStatueHealingPanel(current);panelPoll++) {
                    api.checkStop();await api.sleep(500);current=await observe();
                }
                if(!hasStatueHealingPanel(current))
                    return {status:'stopped',reason:'Verified Statue healing panel did not return after bounded animation wait; no further input sent',heals:healClick+1};
            }
            api.checkStop();await api.keyPress('VK_ESCAPE');await api.sleep(700);current=await observe();
            for(var hpPoll=0;hpPoll<6 && !current.hud.world;hpPoll++){api.checkStop();await api.sleep(350);current=await observe();}
            var restored=current.hud.health;
            if(current.hud.world && restored && restored.current/restored.max>=0.95) {
                var paused=await api.pauseCombat();current=await observe();
                return {status:paused&&current.hud.journal?'completed':'stopped',reason:'Statue healing applied',health:restored,paused:current.hud.journal};
            }
            return {status:'stopped',reason:'Inspect screen after Statue healing',health:restored};
        }
        var statueSpeaker=(current.ocr||[]).some(function(r){return r.text.trim()==='Statue of The Seven' && r.y>830 && r.y<910;});
        if(statueSpeaker) {
            if(!(current.ocr||[]).some(function(r){return /^Statue.s Blessing$/i.test(r.text.trim());})) {
                api.checkStop();await api.keyPress('VK_SPACE');await api.sleep(700);current=await observe();
                for(var optionPoll=0;optionPoll<4 && !(current.ocr||[]).some(function(r){return /^Statue.s Blessing$/i.test(r.text.trim());});optionPoll++){api.checkStop();await api.sleep(350);current=await observe();}
            }
            if((current.ocr||[]).some(function(r){return /^Statue.s Blessing$/i.test(r.text.trim());})) {
                await api.chooseStatueBlessing();await api.sleep(700);current=await observe();
                for(var menuPoll=0;menuPoll<6 && !(current.ocr||[]).some(function(r){return /Click on the character portrait to restore HP/.test(r.text);});menuPoll++){api.checkStop();await api.sleep(350);current=await observe();}
                if((current.ocr||[]).some(function(r){return /Click on the character portrait to restore HP/.test(r.text);})) return await run(current,api,observe,depth+1);
            }
            return {status:'stopped',reason:'Inspect Statue blessing screen'};
        }
        var atStatue=current.hud.world && current.map && current.map.map==='Teyvat' && Math.hypot(current.map.x+1323.474,current.map.y-2566.115)<15;
        if (!atStatue && (!current.hud.journal || !(current.ocr || []).some(function(r){return r.text.trim()==='Going Upon the Breeze';})))
            return {status:'stopped',reason:'Recovery requires the verified Going Upon the Breeze journal'};
        api.checkStop();
        if(!atStatue) {
            await api.keyPress('VK_ESCAPE'); await api.sleep(700);current=await observe();
            for(var closePoll=0;closePoll<4 && !current.hud.world;closePoll++){api.checkStop();await api.sleep(350);current=await observe();}
            atStatue=current.hud.world && current.map && current.map.map==='Teyvat' && Math.hypot(current.map.x+1323.474,current.map.y-2566.115)<15;
            if(!atStatue) {
                await api.keyPress('VK_M'); await api.sleep(150);
                await api.teleportStarfellStatue();
            }
            current = await observe();
            // Native teleport can return during the final white fade; wait for HUD evidence.
            for(var poll=0;poll<12 && !current.hud.world;poll++) {
                api.checkStop();await api.sleep(500);current=await observe();
            }
        }
        var moves=0, turns=0;
        while (current.hud.world && current.map && current.map.map==='Teyvat' && moves<4 && turns<12) {
            api.checkStop();
            var dx=-1323.474-current.map.x,dy=2566.115-current.map.y,distance=Math.hypot(dx,dy);
            if(distance>15) break;
            if(distance<=3) break;
            var target=(Math.atan2(-dy,-dx)*180/Math.PI+360)%360;
            var angle=current.map.cameraAngle;
            if(!Number.isFinite(angle)) break;
            var diff=(angle-target+540)%360-180;
            if(Math.abs(diff)>8) {await api.rotate(Math.max(-250,Math.min(250,Math.round(-8*diff))));turns++;await api.sleep(180);}
            else {await api.forward(500);moves++;await api.sleep(150);}
            current=await observe();
        }
        for(var i=0;i<10 && current.hud.world;i++) {
            if(current.hud.health && current.hud.health.current/current.hud.health.max>=0.95) break;
            api.checkStop();await api.sleep(500);current=await observe();
        }
        unknownStatue=await openUnknownHealthStatue(current,api,observe,depth);
        if(unknownStatue) return unknownStatue;
        var hp=current.hud.health, healed=!!hp && hp.current/hp.max>=0.95;
        if(!healed && current.hud.world && (current.ocr || []).some(function(r){return r.text.trim()==='Statue of The Seven' && r.x>1100 && r.y>400 && r.y<700;})) {
            api.checkStop();await api.keyPress('VK_F');await api.sleep(900);current=await observe();
            for(var statuePoll=0;statuePoll<6 && !(current.ocr||[]).some(function(r){return r.text.trim()==='Statue of The Seven' && r.y>830;});statuePoll++){api.checkStop();await api.sleep(350);current=await observe();}
            if((current.ocr||[]).some(function(r){return r.text.trim()==='Statue of The Seven' && r.y>830;})) return await run(current,api,observe,depth+1);
            return {status:'stopped',reason:'Statue healing menu opened; inspect options',health:hp,moves:moves,turns:turns};
        }
        var paused=await api.pauseCombat();
        if(paused) {current=await observe();paused=current.hud.journal===true;}
        return {status:healed&&paused?'completed':'stopped',reason:healed?'Recovered at Starfell Lake Statue':'Recovery health not verified',health:hp,paused:paused,moves:moves,turns:turns};
    }
    return {run:run, safeClimbingWorld:safeClimbingWorld, safeStatueInteraction:safeStatueInteraction, hasStatueHealingPanel:hasStatueHealingPanel};
})();
if(typeof module!=='undefined'&&module.exports) module.exports=ActOneRecovery;
