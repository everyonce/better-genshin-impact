eval(file.readTextSync('engine.js'));
eval(file.readTextSync('bgi.js'));

(async function () {
    var adapter = createBgiPilotAdapter();
    try {
        var catalog = JSON.parse(file.readTextSync('pilots.json'));
        var plans = JSON.parse(file.readTextSync('plans.json'));
        await EnglishPilots.makeRunner(adapter).run(catalog, plans, settings);
    } finally { adapter.dispose(); }
})();
