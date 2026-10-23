# Local agent streaming prototype

The agent bridge runs inside a BetterGI JavaScript task's existing `TaskRunner` scope. It publishes the latest game frame independently of model inference and file recording. It supports one Windows keyboard/mouse game runtime in a separate RDP child session. Both Windows' actual remote-session flag and BetterGI's explicit `ChildSession` instance role are checked; a console session with ID 2 does not qualify. No numeric Windows session ID is assumed to identify RDP.

Start from an explicitly launched script with:

```javascript
await runAgentBridge("BetterGI.Agent.local", false);
```

The second argument enables input only when explicitly set to `true`. Observe-only mode rejects every action on the server. The application must be built with this host binding. The normal BetterGI stop button and task cancellation end the session. There is no automatic startup, desktop focus acquisition, or secondary controller.

## Transport

Connect to `\\.\pipe\BetterGI.Agent.local`. The pipe allows one client and shares the restricted external controller's pipe factory: explicit current-user access, network-user denial, and a medium-integrity label so an ordinary local client can reach elevated BetterGI. Disconnect ends the task; a later invocation gets a new session ID and input-owner epoch. No TCP listener is opened.

Every packet begins with a 4-byte little-endian JSON byte count followed by UTF-8 JSON. A `frame` response additionally contains exactly `payloadBytes` raw image bytes. There is no base64, PNG compression, or file path on this control path. Client request JSON is limited to 64 KiB and nesting depth 16.

The server immediately sends a `hello` containing:

```json
{
  "type": "hello",
  "version": 1,
  "sessionId": "generated-per-session",
  "ownerEpoch": "generated-per-session",
  "goalVersion": 1,
  "inputEnabled": false,
  "clockFrequency": 1000,
  "captureTimestampKind": "host_capture_request",
  "widthLimit": 640,
  "heightLimit": 360
}
```

`allowedKeys` is also included. All subsequent requests must echo `sessionId`, `ownerEpoch`, and `goalVersion`; `version` defaults to 1. The first prototype has one immutable goal per session. Start a new session to change goals.

The `frame`, `status`, and `stop` commands require only these identity fields and `command`. A frame response includes `frameId`, `capturedAtMs`, `serverNowMs`, RGB `width`/`height`, native `sourceWidth`/`sourceHeight`, `pixelFormat: "rgb24"`, `payloadBytes`, `captureMs`, and `inputAvailable`. Before the first capture it returns `type: "waiting"` with no payload. A backgrounded or minimized game stops publishing; clients must reject repeated or stale frames.

Frames are sampled at a target 30 Hz and fit within 640 by 360 pixels while preserving aspect ratio. A leased buffer pool keeps only the latest publication and any in-flight transport reader. A slow consumer does not grow a queue or force capture to wait. The actual capture rate and game frame age still require measurement. The native backend does not expose a presentation timestamp, so `capturedAtMs` is the host capture-request time rather than the game's render time.

## Action chunks

An example additional action payload is:

```json
{
  "command": "action",
  "requestId": "unique-per-proposal",
  "frameId": 42,
  "observedAtMs": 1000.0,
  "expiresAtMs": 1600.0,
  "modelId": "checkpoint-revision",
  "steps": [
    { "durationMs": 50, "keys": ["W"], "mouseDx": 12, "mouseDy": 0 },
    { "durationMs": 50, "keys": ["W"], "mouseDx": 0, "mouseDy": 0 }
  ]
}
```

Also supply the session identity fields from `hello`. `observedAtMs` must exactly match the referenced server frame. All times use the server's monotonic milliseconds, not Python wall time. The model adapter translates its source units before submission: mouse deltas are relative source-capture pixel-equivalent units. GameScaling's once-per-chunk movement belongs in one step, rather than being repeated at every interval. Mouse sensitivity still needs calibration against the game.

The server requires a frame no older than 500 ms at acceptance, 1–6 intervals of 33–100 ms each, and a total horizon no longer than 250 ms. The full horizon must fit before expiration, which cannot extend beyond capture time plus 750 ms. This is a rejection ceiling, not a latency performance target. Keys and deltas are validated, operating-system escape combinations are rejected, and request IDs remain in the replay cache through the maximum possible validity window of their source frames. Expired entries are pruned, so sustained operation has no lifetime action-count limit. An overload limit of 4,096 simultaneously recent accepted proposals bounds memory.

Input runs on an independent approximately 10 ms scheduling loop. Each interval specifies the complete desired held state. Mouse movement occurs once on interval entry. A valid new proposal replaces the old chunk; missed schedules cancel instead of bursting overdue input. Completion, expiry, focus loss, viewport resize, disconnect, and cancellation release held input. The controller never extends a model's previous action simply because inference is late.

An `accepted` response confirms validation and includes `receivedAtMs`; it does not assert that the game responded. Actual issued transitions arrive in `receipts` on frame/status/stop responses:

```json
{
  "requestId": "unique-per-proposal",
  "modelId": "checkpoint-revision",
  "frameId": 42,
  "status": "completed",
  "reason": "horizon_complete",
  "acceptedAtMs": 1100.0,
  "endedAtMs": 1200.0,
  "appliedSteps": [
    { "index": 0, "startedAtMs": 1100.0, "keys": ["W"], "mouseDx": 12, "mouseDy": 0 },
    { "index": 1, "startedAtMs": 1150.0, "keys": ["W"], "mouseDx": 0, "mouseDy": 0 }
  ]
}
```

Receipt times describe backend input issuance, not an acknowledgment from the game engine. `replaced` preserves held-state continuity until the next accepted interval; other endings release input. Consumers must reconstruct the complete timeline across receipts. Receipts are retained in a bounded 256-entry queue, drained by each frame/status response. `droppedReceipts` makes overflow visible; any affected dataset segment must be excluded or marked incomplete. A transport failure can leave final receipts undelivered and must also invalidate the incomplete segment.

## Validation and limits

`AgentActionControllerTests` exercises real held-state changes on a fake input backend, release on focus loss/deadline/disconnect/resize, replay rejection, malformed coordinates/keys, action replacement, late scheduling, immutable proposals, and bounded receipt overflow. These tests send no Windows input. Live RDP throughput and controlled gameplay remain separate validation steps.

This bridge provides a continuous observation and automated-action interface. Human input hooks, reliable quest completion labels, game-state resets, model skill quality, and visual alignment of recorded demonstrations are separate work. Its timing limits do not establish that either pretrained model meets the direct-control latency target on this GPU.
