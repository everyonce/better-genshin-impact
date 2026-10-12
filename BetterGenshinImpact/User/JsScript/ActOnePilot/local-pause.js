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
      catch (error) { note('pauseObserve', error); await safeRecover('capture failed'); return null; }
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
        var releasedThisCycle = await confirmedRelease();
        var o = await observe();
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

            if (releasedThisCycle && inputIndex < KEYS.length && now - lastInputAt >= INPUT_GAP_MS) {
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
                // The next pass captures again before any other input.
              }
            }
          }
        } else {
          await safeRecover('stale or invalid observation');
        }
        if (now - lastHeartbeat >= 5000) { lastHeartbeat = now; await pending(); }
        try { await api.sleep(250); } catch (error) { note('sleep', error); }
      }
    })();
  }

  return Object.freeze({ ensure: ensure });
});
