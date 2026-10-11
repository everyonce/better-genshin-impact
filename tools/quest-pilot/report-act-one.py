#!/usr/bin/env python3
"""Summarize saved Act One pilot telemetry without exposing OCR or account IDs."""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = (
    REPO_ROOT
    / "artifacts"
    / "release-r8"
    / "BetterGI-English-win-x64"
    / "User"
    / "JsScript"
    / "ActOnePilot"
)


def read_json(path: Path) -> Any | None:
    """Read complete JSON files and ignore files concurrently being written."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    # Nearest-rank percentile; p95 is stable and well-defined for small samples.
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def time_summary(timestamp: int | float | None) -> str | None:
    if not isinstance(timestamp, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(timestamp / 1000, timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def valid_objects(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, list):
        return (item for item in data if isinstance(item, dict))
    return ()


def read_report_objects(path: Path) -> list[dict[str, Any]]:
    """Prefer complete append-only JSONL evidence; tolerate a partial final line."""
    if path.suffix.lower() == ".jsonl":
        content = path.read_text(encoding="utf-8")
        records = []
        lines = content.splitlines(keepends=True)
        for index, line in enumerate(lines):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                is_unterminated_final_fragment = index == len(lines) - 1 and not line.endswith(("\n", "\r"))
                if is_unterminated_final_fragment:
                    continue
                raise ValueError(f"Invalid JSONL record at {path}:{index + 1}") from exc
            if isinstance(value, dict):
                records.append(value)
        return records
    return list(valid_objects(read_json(path)))


def summarize_session(session: str, report_path: Path, observations_dir: Path) -> dict[str, Any]:
    records = read_report_objects(report_path)
    observations: list[dict[str, Any]] = []
    if observations_dir.is_dir():
        for path in observations_dir.glob("frame-*.json"):
            frame = read_json(path)
            if isinstance(frame, dict) and frame.get("session") == session:
                observations.append(frame)
    observations.sort(key=lambda item: (item.get("timestamp", 0), item.get("frameId", 0)))

    # Collapse start/terminal records to one result per mission id. This avoids
    # counting a started record as a separate mission outcome.
    by_mission: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        mission_id = record.get("id")
        if isinstance(mission_id, str):
            by_mission[mission_id].append(record)

    outcomes: Counter[str] = Counter()
    reasons: dict[str, Counter[str]] = defaultdict(Counter)
    input_events: dict[str, Counter[str]] = defaultdict(Counter)
    key_counts: dict[str, Counter[str]] = defaultdict(Counter)
    turns: Counter[str] = Counter()
    durations: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for entries in by_mission.values():
        terminal = next(
            (entry for entry in reversed(entries) if entry.get("status") in {"completed", "failed", "stopped"}),
            None,
        )
        if terminal is None:
            continue
        status = terminal["status"]
        outcomes[status] += 1
        mission_name = terminal.get("mission")
        mission_name = mission_name if isinstance(mission_name, str) else "unknown"
        details = terminal.get("details")
        if not isinstance(details, dict):
            details = {}
        reason = details.get("reason")
        if status != "completed" and isinstance(reason, str) and reason:
            reasons[status][reason] += 1

        result = details.get("result")
        if isinstance(result, dict) and isinstance(result.get("turns"), (int, float)):
            turns[mission_name] += int(result["turns"])
        events = details.get("inputEvents")
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict):
                continue
            kind = event.get("type")
            if not isinstance(kind, str):
                continue
            input_events[mission_name][kind] += 1
            if kind == "key":
                key = event.get("key")
                if isinstance(key, str):
                    key_counts[mission_name][key] += 1
                requested = event.get("durationMs")
                started = event.get("startedAt")
                finished = event.get("finishedAt")
                if isinstance(requested, (int, float)) and isinstance(started, (int, float)) and isinstance(finished, (int, float)):
                    durations[mission_name][str(requested)].append(max(0, finished - started))

    timestamps = [frame.get("timestamp") for frame in observations if isinstance(frame.get("timestamp"), (int, float))]
    first_ts = min(timestamps) if timestamps else None
    last_ts = max(timestamps) if timestamps else None
    timing_stages = ("captureMs", "ocrMs", "pngWriteMs", "mapMs", "totalMs")
    stage_samples: dict[str, list[float]] = defaultdict(list)
    for frame in observations:
        timing = frame.get("timings")
        if not isinstance(timing, dict):
            continue
        for stage in timing_stages:
            value = timing.get(stage)
            if isinstance(value, (int, float)):
                stage_samples[stage].append(value)
    first_map = next(
        (frame for frame in observations if isinstance(frame.get("map"), dict)),
        None,
    )
    first_map_timings = first_map.get("timings") if first_map else None
    first_map_lookup_ms = (
        first_map_timings.get("mapMs")
        if isinstance(first_map_timings, dict) and isinstance(first_map_timings.get("mapMs"), (int, float))
        else None
    )
    time_until_first_map_ms_including_idle = None
    if first_map is not None and isinstance(first_map.get("timestamp"), (int, float)) and first_ts is not None:
        time_until_first_map_ms_including_idle = max(0, first_map["timestamp"] - first_ts)

    final_frame = observations[-1] if observations else {}
    hud = final_frame.get("hud")
    hud = hud if isinstance(hud, dict) else {}
    final_map = final_frame.get("map")
    # Whitelist only map telemetry fields, never OCR/screenshot paths or other frame data.
    safe_map = None
    if isinstance(final_map, dict):
        safe_map = {key: final_map[key] for key in ("x", "y", "map", "cameraAngle") if key in final_map}
    objectives = hud.get("objectives")
    safe_objectives = [value for value in objectives if isinstance(value, str)] if isinstance(objectives, list) else []

    duration_summary: dict[str, Any] = {}
    for mission_name, by_requested in sorted(durations.items()):
        duration_summary[mission_name] = {}
        for requested, actual in sorted(by_requested.items(), key=lambda pair: float(pair[0])):
            duration_summary[mission_name][requested] = {
                "count": len(actual),
                "actual_ms_min": min(actual),
                "actual_ms_median": statistics.median(actual),
                "actual_ms_p95": percentile(actual, 0.95),
                "actual_ms_max": max(actual),
            }

    timing_summary = {}
    for stage in timing_stages:
        values = stage_samples.get(stage, [])
        timing_summary[stage.removesuffix("Ms")] = {
            "sample_count": len(values),
            "median_ms": statistics.median(values) if values else None,
            "p95_ms": percentile(values, 0.95),
        }

    return {
        "session": session,
        "time_basis": "observation timestamps; elapsed includes idle time",
        "first_observation_utc": time_summary(first_ts),
        "last_observation_utc": time_summary(last_ts),
        "elapsed_ms_including_idle": max(0, last_ts - first_ts) if first_ts is not None and last_ts is not None else None,
        "mission_outcomes": {status: outcomes[status] for status in ("completed", "failed", "stopped")},
        "mission_reasons": {status: dict(sorted(counts.items())) for status, counts in sorted(reasons.items())},
        "controller_emitted_input": {
            "event_counts_by_mission": {name: dict(sorted(counts.items())) for name, counts in sorted(input_events.items())},
            "key_counts_by_mission": {name: dict(sorted(counts.items())) for name, counts in sorted(key_counts.items())},
            "turns_by_mission": dict(sorted(turns.items())),
            "interpretation": "navigation is autonomous route input; keyPress may be supervised menu or steering input",
        },
        "key_duration_ms_by_mission_and_requested_duration": duration_summary,
        "observation_stage_timing": timing_summary,
        "first_map_lookup_ms": first_map_lookup_ms,
        "time_until_first_map_ms_including_idle": time_until_first_map_ms_including_idle,
        "first_map_frame_id": first_map.get("frameId") if first_map else None,
        "terminal_observation_evidence": {
            "frame_id": final_frame.get("frameId"),
            "map": safe_map,
            "hud_objectives": safe_objectives,
            "interpretation": "last observed quest objective only; not a completion claim",
        },
    }


def build_report(root: Path) -> dict[str, Any]:
    reports_dir = root / "reports"
    observations_root = root / "observations"
    sessions = []
    if reports_dir.is_dir():
        report_paths = {}
        for report_path in reports_dir.glob("*.json"):
            report_paths[report_path.stem] = report_path
        for report_path in reports_dir.glob("*.jsonl"):
            report_paths[report_path.stem] = report_path
        for session, report_path in sorted(report_paths.items()):
            sessions.append(summarize_session(session, report_path, observations_root / session))
    return {
        "scope": "saved Act One pilot telemetry",
        "privacy": "OCR text, screenshots, and account identifiers are omitted",
        "elapsed_note": "Runtime interval includes idle time and does not mean the quest completed.",
        "sessions": sessions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write JSON summary here (default: print to stdout)")
    parser.add_argument("--artifact-root", type=Path, default=ARTIFACT_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()
    serialized = json.dumps(build_report(args.artifact_root), ensure_ascii=False, indent=2) + "\n"
    if args.output is None:
        print(serialized, end="")
        return 0

    destination = args.output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary.write(serialized)
            temporary_path = temporary.name
        os.replace(temporary_path, destination)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
