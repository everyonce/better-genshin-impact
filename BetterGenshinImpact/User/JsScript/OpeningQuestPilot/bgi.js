function createOpeningQuestAdapter() {
    function release(obj) { if (obj && typeof obj.dispose === 'function') obj.dispose(); }
    function requireSize(w, h) {
        if (genshin.isRemoteDesktopSession !== true) throw new Error('RDP session required.');
        if (Number(w) !== 1920 || Number(h) !== 1080) throw new Error('Opening Quest Pilot requires a 1920x1080 game capture.');
    }
    function requireInputReady() {
        if (genshin.isRemoteDesktopSession !== true) throw new Error('RDP session required.');
        if (genshin.isGameForeground !== true) throw new Error('Game lost foreground focus; stopping input.');
    }
    return {
        now: function () { return Date.now(); },
        sleep: function (ms) { return sleep(ms); },
        focusGame: async function () {
            if (genshin.isRemoteDesktopSession !== true) throw new Error('RDP session required.');
            if (typeof genshin.focusGame !== 'function') throw new Error('Opening Quest Pilot requires English BetterGI r8 or newer.');
            await genshin.focusGame();
            requireInputReady();
        },
        requireInputReady: requireInputReady,
        keyPress: function (key) { requireInputReady(); keyPress(key); },
        keyDown: function (key) { requireInputReady(); keyDown(key); },
        keyUp: function (key) { keyUp(key); },
        moveMouseBy: function (x, y) { requireInputReady(); moveMouseBy(x, y); },
        click: function (x, y) { requireInputReady(); click(x, y); },
        requireSize: requireSize,
        write: function (path, text, append) {
            if (!file.writeTextSync(path, text, append === true)) throw new Error('Cannot write ' + path);
        },
        capture: function (path) {
            var timestamp = Date.now(), image = captureGameRegion(), found = null, rows = [];
            try {
                requireSize(image.width, image.height);
                if (!file.writeImageSync(path, image.srcMat)) throw new Error('Cannot write screenshot ' + path);
                found = image.findMulti(RecognitionObject.Ocr(0, 0, 1920, 1080));
                for (var i = 0; i < found.count; i++) {
                    var row = found[i];
                    rows.push({ text: String(row.text), x: Number(row.x), y: Number(row.y),
                        width: Number(row.width), height: Number(row.height) });
                }
                var nav = { rdp: genshin.isRemoteDesktopSession, windowsSessionId: genshin.windowsSessionId };
                try {
                    var position = genshin.getPositionFromMap();
                    nav.position = position ? { x: Number(position.x), y: Number(position.y) } : null;
                    nav.cameraAngle = Number(genshin.getCameraOrientation());
                } catch (error) { nav.error = String(error); }
                if (!file.writeTextSync('navigation.json', JSON.stringify(nav))) throw new Error('Cannot write navigation.json');
                return { timestamp: timestamp, width: Number(image.width), height: Number(image.height), ocr: rows };
            } finally {
                try { if (found) for (var j = 0; j < found.count; j++) release(found[j]); }
                finally { release(image); }
            }
        }
    };
}
