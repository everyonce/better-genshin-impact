# Offline P2P three-arm replay

This package contains the source needed to reproduce the bounded, sequential
history-sensitivity experiment from a fresh fork checkout. It runs **CPU preflight
by default**. Only `--execute-gpu` loads the policy. It has no game, capture, pipe,
controller, resident-session or training path.

The supported entrypoint is `p2p_replay_forward_sequential.py`. The other two replay
modules preserve numerical helpers and their original historical entrypoints;
those older entrypoints are not the packaged workflow and may require their
original experiment artifacts. The sequential helper is byte-identical to the
validated source. Tests compare every retained numerical function/class against
the source-segment hashes in `historical-provenance.json`.

This is a newly packaged source artifact, **not** the runner that already produced
the historical result. Changes are limited to decoder-path resolution, explicit
hash-bound goal-file relocation, dependency metadata and historical-summary
loading. The validated replay, sampler, exact parity checks and publication gates
are unchanged. The small historical JSON contains hashes and gate summaries,
not the original report, images, weights or NPZ arrays. Its gates are never counted
as validation of a new run.

## Inputs and dependencies

Supply these files yourself; the runner does not download or install anything:

- A **complete old-style single episode** report plus `observations.jsonl`,
  `frames.jsonl`, `events.jsonl`, `recording.json` and `frames.mp4`. Arbitrary resident
  rollover parts and newer recording schemas are not supported by the current
  preparer. Loss, ambiguous clocks, missing receipts, invalid joins or boundaries
  reject affected windows.
- Three locally regenerated [forward plans](../REPLAY_FORWARD.md), selecting
  probes **2392, 711 and 3079**, with 2392 as the identical-input negative control.
  This exact case set is intentional: broadening it would change the validated
  comparison/control contract. You need the corresponding supplied recordings;
  the repository does not include that dataset.
- An Open P2P source checkout at commit
  `a329d98cbe62119679a254d71bea6446773541bc` from
  [the official repository](https://github.com/elefant-ai/open-p2p). The runner
  verifies its Git revision and records source-file hashes.
- For GPU execution, the released 150M
  `checkpoint-step=00500000.ckpt` and adjacent `model_config.yaml`. The existing
  [download utility](../download-models.py) identifies the pinned release as
  `guaguaa/open-p2p`, revision `de18b62bc8f9722bda64497600c38c8f7634d86b`.
  Loading is tensor-only and strict, with no random-weight fallback. The supplied
  checkpoint/config hashes are recorded by every GPU run.
- Local FFmpeg and FFprobe executables, supplied explicitly or available on PATH.
  Decoding is CPU-only, by absolute frame index; actual PTS/counts are checked.
- Every recorded goal artifact, if the episode has text conditioning. No encoder
  is loaded: the recorded vector and metadata are reused.

CPU preflight/tests use Python, NumPy, Pillow and PyTorch CPU tensor operations.
GPU execution also needs a compatible CUDA PyTorch/Torchvision pair, PyYAML,
pydantic, pydantic-yaml, fsspec, protobuf and einops, with their normal dependencies.
The historical environment was Windows x64, Python 3.11.9,
PyTorch 2.7.1+cu128, Torchvision 0.22.1+cu128, NumPy 2.4.6, Pillow 12.3.0,
PyYAML 6.0.3, pydantic 2.14.1, pydantic-yaml 1.7.0, fsspec 2026.7.0,
protobuf 7.36.2 and einops 0.8.2. No installer is included. New reports record
installed versions; exact historical numerical results on a different runtime
or GPU are not promised.

The remaining source closure is already tracked in the parent directory:
`prepare_replay.py`, `prepare_replay_forward.py`, `observation_profiles.py`,
`goal_embedding.py`, `p2p_loader.py`, `p2p_compat_attention.py` and `p2p_rotary.py`.
The runner hashes `model_adapters.py` and `stream_client.py` as provenance only;
it does not import or invoke their live-policy paths. Tests also reuse the tracked
`test_prepare_replay.py` evidence fixture. No ignored experiment **source** is
needed.

## Prepare local plans and run

Run from the fork root. Set the variables below to your supplied files and an
existing suitable Python environment. Use a new output directory for each run:
the runner refuses to overwrite earlier results.

```powershell
$agentPython = 'C:/path/to/python.exe'
$openP2pSource = 'C:/data/open-p2p'
$checkpointFile = 'C:/data/open-p2p-150M/150M/checkpoint-step=00500000.ckpt'
$episodeReport = 'C:/data/r14-native/report.json'
$episodeDir = 'C:/data/r14-native/recording'
$replayRoot = 'artifacts/replay-local'
$ffmpegPath = 'C:/path/to/ffmpeg.exe'
$ffprobePath = 'C:/path/to/ffprobe.exe'

foreach ($probeId in 2392, 711, 3079) {
    & $agentPython tools/bettergi-agent/prepare_replay_forward.py `
      --report $episodeReport --recording-dir $episodeDir `
      --probe-frame-id $probeId --max-windows 1 `
      --output "$replayRoot/probe-$probeId.json"
    if ($LASTEXITCODE -ne 0) { throw 'Replay preparation failed; inspect its rejection report.' }
}

$replayArgs = @(
    'tools/bettergi-agent/experiments/p2p_replay_forward_sequential.py',
    '--case', "$replayRoot/probe-2392.json", '2392',
    '--case', "$replayRoot/probe-711.json", '711',
    '--case', "$replayRoot/probe-3079.json", '3079',
    '--negative-control-probe', '2392', '--source', $openP2pSource,
    '--checkpoint', $checkpointFile, '--ffmpeg', $ffmpegPath, '--ffprobe', $ffprobePath
)
& $agentPython @replayArgs --output "$replayRoot/cpu-preflight-001"
```

Regenerating plans binds the unchanged supplied evidence and current preparer
paths/hashes. It does not bypass evidence checks or repair rejected input. Never
edit historical recordings/reports to make an old plan pass. A changed preparer,
input file, goal metadata or video join still fails closed.

If a recorded goal has moved, add an explicit mapping **before either run**:

```powershell
$replayArgs += @('--goal-artifact', 'D:/recorded/original-goal.json',
                 'C:/data/copied-goal.json', '<independently-retained-original-SHA256>')
```

The first path must match the recorded metadata exactly. The local file must
match the supplied SHA-256, and every non-path metadata field must remain equal.
Duplicate, unknown and unused mappings fail. Use the digest from independently
retained original evidence, such as an earlier run's `goalEvidence.fileEvidence`;
hashing an arbitrary replacement merely to satisfy this flag is not proof of
the original embedding. Old recordings did not attest embedding bytes. Output
therefore records `identitySource: caller-supplied-sha256` and
`recordingAttestsArtifactHash: false`, retaining the original path/provenance.
Without an independent identity, leave current-path behavior unchanged or stop;
do not claim a verified migration.

After inspecting a successful CPU preflight, the explicitly opted-in offline
model command is:

```powershell
& $agentPython @replayArgs --output "$replayRoot/gpu-run-001" --execute-gpu
```

This decodes and rechecks inputs again, loads one isolated 41-frame checkpoint,
and uses the original `online_forward` supplied-action path for all three arms.
There are always 40 real history images plus the unlabelled probe and 32 paired
seeds per arm. Both replay passes must have exact contexts, all history logits and
the first probe head. Later probe teacher-forced heads may depend on the changed
placeholder and are explicitly diagnostic. Every complete sampled eight-token
action, decoded action and conditional logit must repeat exactly. All three
negative-control pairs must match. **No comparison is published until every
case/arm/seed passes.**

The original full-context-versus-incremental test failed its 1e-3 gate. This
sequential experiment does not establish or waive it:
`fullContextParityEstablished` remains false. Following acquisition approximates
the official image-j/annotation-j+1 index direction, not exact Recap callback
timing or physical input. The sampler is raw/unmasked; controller whole-proposal
admission is absent. Supplied histories, lossy video, cold context and 32 seeds
limit interpretation. Reports remain offline, system/model provenance only,
`trainingEligible: false`, `productionEligible: false`, with no human/expert,
gameplay success or live-policy improvement claim.

## CPU verification

```powershell
$env:P2P_SOURCE = $openP2pSource
$env:P2P_FFMPEG = $ffmpegPath
$env:P2P_FFPROBE = $ffprobePath
& $agentPython -m unittest discover -s tools/bettergi-agent/experiments -p 'test_*.py' -v
```

Tests use CPU tensors and bounded synthetic video only, never policy construction
or CUDA. Source-dependent and decoder-dependent checks explicitly skip when the
supplied tools are absent; inspect skip counts. Other checks cover byte/source
identity, exact failure gates, negative controls, reconstruction, source-only
checkout import and goal relocation with changed-embedding rejection.
