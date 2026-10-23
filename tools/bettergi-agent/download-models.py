"""Download benchmark checkpoints and record their exact provenance locally."""

import argparse
import hashlib
import json
import os
from pathlib import Path


def main():
    """Download the benchmarked model revisions and hash the weights."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2] / "artifacts" / "agent")
    parser.add_argument("--model", choices=["all", "gamescaling", "open-p2p"], default="all")
    args = parser.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(args.root / "hf-cache"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    from huggingface_hub import snapshot_download

    candidates = [
        ("gamescaling", "THUSI-Lab/GameScaling-0.8B-S3", "GameScaling-0.8B-S3",
         "1b89640dcf2ef51fb53ad9338a0725e9622dd200", None),
        # The official Open P2P download script names this release repository.
        ("open-p2p", "guaguaa/open-p2p", "open-p2p-150M",
         "de18b62bc8f9722bda64497600c38c8f7634d86b", ["150M/*"]),
    ]
    for name, repo, directory, revision, patterns in candidates:
        if args.model not in ("all", name):
            continue
        destination = args.root / "models" / directory
        snapshot_download(repo, revision=revision, local_dir=destination, allow_patterns=patterns, max_workers=2)
        weights = {}
        for file in destination.rglob("*"):
            if file.suffix in (".safetensors", ".ckpt"):
                with file.open("rb") as stream:
                    weights[str(file.relative_to(destination))] = hashlib.file_digest(stream, "sha256").hexdigest()
        manifest = {"repository": repo, "revision": revision, "weightsSha256": weights}
        (destination / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()
