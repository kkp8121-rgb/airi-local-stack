"""Run external api_v2.py after installing AIRI's guarded cache overlay."""
from __future__ import annotations
import argparse, os, runpy, sys
from pathlib import Path
from v2proplus_sv_embedding_cache_overlay import PINNED_TTS_SHA256, install
parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("--external-root", type=Path, required=True)
parser.add_argument("--tts-sha256", default=os.environ.get("AIRI_GPT_SOVITS_TTS_SHA256", PINNED_TTS_SHA256))
args, api_args = parser.parse_known_args()
root = args.external_root.resolve(); api = root / "api_v2.py"
if not api.is_file(): raise SystemExit(f"api_v2.py not found: {api}")
if api_args[:1] == ["--"]: api_args = api_args[1:]
sys.path[:0] = [str(root), str(root / "GPT_SoVITS")]
install(root, args.tts_sha256)
sys.argv = [str(api), *api_args]
runpy.run_path(str(api), run_name="__main__")
