var ActTwoInteraction = (function(){
    function selection(rows,name){
        var labels=(rows||[]).filter(function(r){return r.text===name&&r.x>=1150&&r.x<=1500&&r.y>=450&&r.y<=620;}),
            prompts=(rows||[]).filter(function(r){return r.text==='F'&&r.x>=1080&&r.x<=1170&&r.y>=450&&r.y<=620;});
        if(labels.length!==1||!prompts.length)return null;
        var y=labels[0].y+labels[0].height/2,deltas=prompts.map(function(r){return y-(r.y+r.height/2);});
        if(deltas.every(function(d){return Math.abs(d)<25;}))return 'selected';
        if(deltas.every(function(d){return d>40&&d<100;}))return 'next';
        return null;
    }
    return {selection:selection};
})();
if(typeof module!=='undefined'&&module.exports)module.exports=ActTwoInteraction;
