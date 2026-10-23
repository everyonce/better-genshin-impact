// Keep capture and bounded input execution inside BetterGI's existing task owner.
(async function () {
    const enableInput = settings.enableInput === true || settings.enableInput === "true";
    log.info("Starting local agent stream. Input enabled: " + enableInput);
    await runAgentBridge("BetterGI.Agent.local", enableInput);
})();
