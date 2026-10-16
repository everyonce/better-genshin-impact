(function (root, factory) {
  var api = factory();
  root.ActOneLocalPause = api;
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var KEYS = ['VK_B', 'VK_J', 'VK_ESCAPE'];
  var FRESH_MS = 1000;
  var INPUT_GAP_MS = 750;

  function clone(value) {
    if (value === null || typeof value !== 'object') return value;
    var copy = Array.isArray(value) ? [] : {};
    Object.keys(value).forEach(function (key) { copy[key] = clone(value[key]); });
    return copy;
  }

  function freeze(value) {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
      Object.keys(value).forEach(function (key) { freeze(value[key]); });
      Object.freeze(value);
    }
    return value;
  }

  function ensure(request, api) {
    if (!request || typeof request.session !== 'string' || !request.session || !api)
      return Promise.reject(new Error('local pause requires a pinned session and API'));
    var session = request.session;
    var afterFrame = request.afterFrameId;
    if (!Number.isInteger(afterFrame) || afterFrame < 0)
      return Promise.reject(new Error('local pause requires a nonnegative integer afterFrameId'));
    var lastFrame = afterFrame;
    var lastTimestamp = -Infinity;
    var lastInputAt = -Infinity;
    var inputIndex = 0;
    var sourceFrame = afterFrame;
    var events = 0;
    var lastHeartbeat = -Infinity;
    var errors = [];
    var startedAt = api.now();
    var seed = request.initialObservation || null;

    function note(where, error) {
      if (errors.length < 20) errors.push({ where: where, error: String(error && error.message || error) });
    }
    async function pending() {
      if (typeof api.pausePending !== 'function') return;
      try {
        await api.pausePending({ session: session, events: events, attempts: inputIndex,
          lastFrameId: lastFrame, errors: errors.slice(), waiting: true });
      } catch (error) { note('pausePending', error); }
    }
    function fresh(o, now) {
      return Number.isFinite(now) && !!o && o.session === session && Number.isInteger(o.frameId) && o.frameId >= 0 && o.frameId > lastFrame &&
        Number.isFinite(o.timestamp) && o.timestamp > lastTimestamp && o.timestamp <= now && now - o.timestamp <= FRESH_MS;
    }
    async function safeRecover(reason) {
      if (typeof api.pauseRecoverFocus !== 'function') return;
      try { await api.pauseRecoverFocus(session, { reason: reason, readOnly: true }); }
      catch (error) { note('pauseRecoverFocus', error); }
    }
    async function observe() {
      try { return await api.pauseObserve(); }
      catch (error) {
        if(error&&error.code==='CAPTURE_STORAGE_BLOCKED'){await confirmedRelease();throw error;}
        note('pauseObserve', error); await safeRecover('capture failed'); return null;
      }
    }
    async function proofFor(o) {
      try {
        var proof = await api.pauseProof(o);
        if (!proof) return null;
        if (!proof || !['inventory', 'journal', 'domain', 'menu', 'party', 'map'].includes(proof.kind) ||
            !Array.isArray(proof.evidence) || proof.evidence.length === 0)
          throw new Error('pauseProof returned an invalid proof');
        var result = clone({ verified: true, session: session, sourceFrameId: sourceFrame,
          pauseFrameId: o.frameId, timestamp: o.timestamp, kind: proof.kind, evidence: proof.evidence });
        return freeze(result);
      } catch (error) { note('pauseProof', error); return null; }
    }
    async function confirmedRelease() {
      try { await api.release(); return true; }
      catch (error) { note('release', error); return false; }
    }

    return (async function watchdog() {
      while (true) {
        // A blocked dialogue must not own the controller and write frames forever.
        // Leave a failure, never a synthetic pause proof. The caller latches a fault.
        if (events >= 120 || api.now() - startedAt >= 60000) {
          await confirmedRelease();
          await pending();
          var exhausted = new Error('Pause protection exhausted: pause is UNVERIFIED; operator intervention required');
          exhausted.code = 'PAUSE_PROTECTION_EXHAUSTED';
          throw exhausted;
        }
        var releasedThisCycle = await confirmedRelease();
        // A caller may hand off its just-observed post-action frame. It must
        // pass the same session/freshness checks, and adapter input readiness
        // still binds it to the current captured frame and foreground game.
        var reused = !!seed && fresh(seed, api.now());
        var o = reused ? seed : await observe();
        seed = null;
        events = Math.min(events + 1, 1000000);
        var now;
        try { now = api.now(); } catch (error) { now = Date.now(); note('now', error); }
        if (o && o.session !== session) {
          await safeRecover('session changed');
        } else if (fresh(o, now)) {
          lastFrame = o.frameId;
          lastTimestamp = o.timestamp;
          var verified = await proofFor(o);
          if (verified) {
            if (releasedThisCycle) return verified;
          } else {
            if (releasedThisCycle && typeof api.pauseDialogueHandoff === 'function' && await api.pauseDialogueHandoff(o))
              return freeze({conversationActive:true,session:session,frameId:o.frameId,timestamp:o.timestamp});

            if (releasedThisCycle && now - lastInputAt >= INPUT_GAP_MS) {
              var knownUiResult = null;
              var knownUiFailed = false;
              if (typeof api.pauseResolveKnownUi === 'function') {
                // The hook may resolve a specific known UI state; it cannot establish pause proof.
                verified = await proofFor(o);
                if (verified) {
                  if (releasedThisCycle) return verified;
                } else {
                  try { knownUiResult = await api.pauseResolveKnownUi(o); }
                  catch (error) {
                    note('pauseResolveKnownUi', error);
                    knownUiFailed = true;
                    await safeRecover('known UI resolution failed');
                  }
                  if (knownUiResult === true) {
                    lastInputAt = now;
                    sourceFrame = o.frameId;
                    knownUiFailed = true; // Always observe a new frame before any pause-key fallback.
                  }
                }
              }
              if (inputIndex < KEYS.length && !knownUiFailed && knownUiResult !== true) {
              var ready = false;
              try { ready = !!(await api.pauseInputReady(o)); }
              catch (error) { note('pauseInputReady', error); }
              // Re-check pause recognition immediately before any input. A recognized menu is input-proof.
              verified = await proofFor(o);
              if (verified) {
                if (releasedThisCycle) return verified;
              } else if (ready) {
                var key = KEYS[inputIndex++]; // Count before awaiting: a throwing key-down still consumes the key.
                lastInputAt = now;
                sourceFrame = o.frameId;
                try { await api.pauseKey(o, key, 60); }
                catch (error) { note('pauseKey', error); }
                if (reused) await api.sleep(650);
                // The next pass captures again before any other input.
              }
              }
            }
          }
        } else {
          await safeRecover('stale or invalid observation');
        }
        if (now - lastHeartbeat >= 5000) { lastHeartbeat = now; await pending(); }
        try { await api.sleep(events < 8 ? 250 : events < 32 ? 1000 : 5000); } catch (error) { note('sleep', error); }
      }
    })();
  }

  return Object.freeze({ ensure: ensure });
});
