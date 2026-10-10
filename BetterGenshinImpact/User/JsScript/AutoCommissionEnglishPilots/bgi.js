// BetterGI adapter. No game action happens until an adapter method is called.
function createBgiPilotAdapter() {
    var hudMat = null, previousMetrics = null;
    function release(obj) { if (obj && typeof obj.dispose === 'function') obj.dispose(); }
    function rows(region, box) {
        var found = region.findMulti(RecognitionObject.Ocr(box[0], box[1], box[2], box[3]));
        var result = [];
        try {
            for (var i = 0; i < found.count; i++) {
                var row = found[i];
                result.push({ text: String(row.text), x: Number(row.x), y: Number(row.y),
                    width: Number(row.width), height: Number(row.height) });
            }
        } finally { for (var j = 0; j < found.count; j++) release(found[j]); }
        return result;
    }
    function capture() {
        var image = captureGameRegion(), hud = null;
        try {
            if (!hudMat) hudMat = file.readImageMatSync('assets/paimon_menu.png');
            hud = image.find(RecognitionObject.TemplateMatch(hudMat, 0, 0, 300, 230));
            var inWorld = !hud.isEmpty();
            return { hud: inWorld,
                interactions: inWorld ? rows(image, [1050, 220, 720, 650]) : [],
                options: inWorld ? [] : rows(image, [1100, 200, 780, 710]),
                completion: rows(image, [540, 110, 900, 350]) };
        } finally { release(hud); release(image); }
    }
    function clickRow(row) {
        click(Math.round(row.x + row.width / 2), Math.round(row.y + row.height / 2));
    }
    return {
        read: function (path) { return file.readTextSync(path); },
        info: function (text) { log.info(text); },
        now: function () { return Date.now(); },
        sleep: function (ms) { return sleep(ms); },
        key: function (key) { keyPress(key); },
        click: clickRow,
        capture: capture,
        journal: function () {
            var image = captureGameRegion();
            try { return rows(image, [40, 80, 1840, 880]); } finally { release(image); }
        },
        metrics: function () { return [genshin.width, genshin.height]; },
        interact: async function (row) {
            await sleep(1);
            keyDown('VK_MENU');
            try { await sleep(200); clickRow(row); }
            finally { keyUp('VK_MENU'); }
            await sleep(650);
        },
        enableDialogue: function () {
            previousMetrics = getGameMetrics();
            setGameMetrics(1920, 1080, 1);
            var config = new AutoSkipConfig();
            config.enabled = true;
            config.quicklySkipConversationsEnabled = true;
            // Stable internal enum string; deliberately not a translated display label.
            config.clickChatOption = '不选择选项';
            config.skipBuiltInClickOptions = true;
            config.customPriorityOptionsEnabled = false;
            config.customPriorityOptions = '';
            config.submitGoodsEnabled = false;
            config.autoGetDailyRewardsEnabled = false;
            config.autoReExploreEnabled = false;
            config.autoHangoutEventEnabled = false;
            config.runBackgroundEnabled = false;
            config.closePopupPagedEnabled = false;
            dispatcher.addTimer(new RealtimeTimer('AutoSkip', config));
        },
        clearDialogue: function () {
            dispatcher.clearAllTriggers();
            if (previousMetrics) setGameMetrics(previousMetrics[0], previousMetrics[1], previousMetrics[2]);
            previousMetrics = null;
        },
        path: async function (json) {
            if (typeof pathingScript.runForQuest !== 'function') {
                throw new Error('This pilot needs the English r6 build or newer (quest-route API). Install the supplied BetterGI update first.');
            }
            await pathingScript.runForQuest(json);
        },
        dispose: function () { release(hudMat); hudMat = null; }
    };
}
