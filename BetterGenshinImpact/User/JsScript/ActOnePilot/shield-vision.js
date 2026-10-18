(function (root) {
    'use strict';
    // Native read-only template observations. Missing matches remain unknown;
    // this module never interprets disappearance as shield removal.
    function read(image, api) {
        function matches(name, scale, rect, threshold) {
            let source = null, resized = null, recognition = null, found = null;
            try {
                source = api.file.readImageMatSync('assets/' + name + '.png');
                resized = scale === 1 ? source : source.resize(new api.cv.Size(
                    Math.round(Number(source.width) * scale), Math.round(Number(source.height) * scale)));
                recognition = api.RecognitionObject.TemplateMatch(resized, ...rect);
                recognition.threshold = threshold;
                recognition.use3Channels = true;
                found = image.findMulti(recognition);
                const values = [];
                for (let i = 0; i < found.count && i < 3; i++) {
                    const r = found[i];
                    values.push({ x: Number(r.x), y: Number(r.y), width: Number(r.width),
                        height: Number(r.height), confidenceLowerBound: threshold, score: Number(r.matchScore), template: name, scale });
                }
                return values;
            } finally {
                if (found) { for (let i = 0; i < found.count; i++) api.dispose(found[i]); api.dispose(found); }
                if (recognition) api.dispose(recognition.templateImageGreyMat);
                if (resized !== source) api.dispose(resized);
                api.dispose(source);
            }
        }
        const wood = [];
        for (const name of (api.aimOnly ? (api.aim ? ['wood-shield-ranged'] : []) : ['wood-shield-face', 'wood-shield-face-oblique', 'wood-shield-ranged']))
            for (const scale of (api.diagnostic ? [.75, 1, 1.25, 1.4, 1.5, 1.6, 1.75, 2] : [.75, 1, 1.25]))
                wood.push(...matches(name, scale, api.diagnostic ? [900, 550, 300, 350] : [200, 280, 1350, 550], api.diagnostic ? .5 : .9));
        if(!api.diagnostic&&(!api.aimOnly||api.aim))for(const scale of [.8,.9,1,1.1,1.2,1.3,1.4])wood.push(...matches('wood-shield-frontal-face',scale,[200,280,1350,550],.9));
        const q = api.aim ? [] : matches('amber-burst-ready-field', 1, [1755, 915, 125, 120], .93).concat(matches('amber-burst-ready-glow', 1, [1755, 915, 125, 120], .93));
        return { wood, amberBurstReady: q.length > 0, burstMatches: q,
            shieldRemovalSupported: false, barrierIdentificationSupported: false };
    }
    root.ShieldVision = { read };
    if (typeof module !== 'undefined' && module.exports) module.exports = root.ShieldVision;
})(typeof globalThis !== 'undefined' ? globalThis : this);
