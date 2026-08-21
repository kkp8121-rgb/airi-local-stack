"""Fail-closed, local-only AIRI GGUF packaging.

This command deliberately does not download models or overwrite artifacts.  It
turns one pinned merged Hugging Face checkpoint into a BF16 GGUF and then a
Q4_K_M GGUF using an explicitly supplied, pinned llama.cpp toolchain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Sequence


class PackagingError(RuntimeError):
    """Raised whenever packaging cannot establish all required evidence."""


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
ApiCall = Callable[[str, str, dict[str, Any] | None], dict[str, Any]]
SHA256 = re.compile(r"[0-9a-f]{64}")
TAG_PREFIX = re.compile(r"(?!-)(?!.*[\x00-\x1f\s])[A-Za-z0-9][A-Za-z0-9._/-]*:[A-Za-z0-9][A-Za-z0-9._-]*$")


def sha256_and_size(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size <= 0:
        raise PackagingError(f"required non-empty file is missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "sha256": digest.hexdigest(), "size_bytes": path.stat().st_size}


def publishable_file_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Keep audit evidence useful without disclosing machine-specific paths."""
    return {"name": Path(str(evidence["path"])).name, "sha256": evidence["sha256"],
            "size_bytes": evidence["size_bytes"]}


def local_existing_path(value: str, label: str, *, directory: bool = False) -> Path:
    # Reject URLs, UNC paths, and common URI spellings before Path normalizes them.
    if ("://" in value or value.startswith(("\\\\", "//"))
            or re.match(r"^[A-Za-z][A-Za-z0-9+.\-]*:[\\/]", value)):
        # A Windows drive is the sole permitted scheme-like prefix.
        if not re.match(r"^[A-Za-z]:[\\/]", value):
            raise PackagingError(f"{label} must be a local path, not a URL or network path")
    path = Path(value)
    if not path.is_absolute():
        raise PackagingError(f"{label} must be an absolute local path")
    if directory:
        if not path.is_dir():
            raise PackagingError(f"{label} must be an existing directory")
    elif not path.is_file():
        raise PackagingError(f"{label} must be an existing file")
    return path.resolve()


def new_local_output(value: str) -> Path:
    if "://" in value or value.startswith(("\\\\", "//")):
        raise PackagingError("output dir must be a local path")
    path = Path(value)
    if not path.is_absolute():
        raise PackagingError("output dir must be an absolute local path")
    path = path.resolve()
    if path.exists():
        raise PackagingError(f"output dir already exists: {path}")
    if not path.parent.is_dir():
        raise PackagingError(f"output dir parent does not exist: {path.parent}")
    return path


def require_pinned_merged_weight(merged_dir: Path, expected_sha256: str) -> dict[str, Any]:
    if not SHA256.fullmatch(expected_sha256):
        raise PackagingError("merged model SHA-256 must be 64 lowercase hexadecimal characters")
    if not (merged_dir / "config.json").is_file():
        raise PackagingError("merged dir must contain config.json")
    weights = sorted(merged_dir.glob("*.safetensors"))
    if len(weights) != 1:
        raise PackagingError("merged dir must contain exactly one .safetensors model weight")
    evidence = sha256_and_size(weights[0])
    if evidence["sha256"] != expected_sha256:
        raise PackagingError("merged model SHA-256 does not match the supplied pin")
    return evidence


def require_file_pin(path: Path, expected_sha256: str, label: str) -> dict[str, Any]:
    if not SHA256.fullmatch(expected_sha256):
        raise PackagingError(f"{label} SHA-256 pin must be 64 lowercase hexadecimal characters")
    evidence = sha256_and_size(path)
    if evidence["sha256"] != expected_sha256:
        raise PackagingError(f"{label} SHA-256 does not match the supplied pin")
    return evidence


def quantizer_bundle_evidence(quantizer: Path, expected_sha256: str) -> dict[str, Any]:
    if not SHA256.fullmatch(expected_sha256):
        raise PackagingError("quantizer bundle SHA-256 pin must be 64 lowercase hexadecimal characters")
    entries: list[dict[str, Any]] = []
    for child in sorted(quantizer.parent.iterdir(), key=lambda item: item.name):
        if child.is_symlink() or not child.is_file():
            raise PackagingError("quantizer bundle parent must contain only regular non-symlink files")
        item = sha256_and_size(child)
        entries.append({"name": child.name, "size_bytes": item["size_bytes"], "sha256": item["sha256"]})
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    if digest != expected_sha256:
        raise PackagingError("quantizer bundle SHA-256 does not match the supplied pin")
    return {"manifest_sha256": digest, "files": entries}


def default_runner(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    # llama.cpp emits UTF-8 even on a Korean Windows console.  Relying on the
    # process ANSI code page can crash subprocess' reader thread (cp949 cannot
    # decode several converter progress glyphs) and silently lose diagnostics.
    return subprocess.run(
        list(command), shell=False, text=True, encoding="utf-8", errors="replace",
        capture_output=True, check=False,
    )


def run_checked(command: Sequence[str], label: str, runner: Runner) -> subprocess.CompletedProcess[str]:
    result = runner(command)
    if result.returncode != 0:
        raise PackagingError(f"{label} failed with exit code {result.returncode}: {result.stderr.strip()}")
    return result


def default_api_call(method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    """Call only Ollama's fixed localhost API; callers cannot select an endpoint."""
    if path not in {"/api/tags", "/api/show"}:
        raise PackagingError("unsupported local Ollama API path")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request("http://127.0.0.1:11434" + path, data=body,
                                     method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            parsed = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        raise PackagingError(f"local Ollama API {path} failed: {exc}") from exc
    if not isinstance(parsed, dict):
        raise PackagingError(f"local Ollama API {path} returned a non-object response")
    return parsed


def exact_tag_record(tags_payload: dict[str, Any], tag: str) -> dict[str, Any] | None:
    models = tags_payload.get("models")
    if not isinstance(models, list):
        raise PackagingError("local Ollama tags response did not contain models")
    matches = [item for item in models if isinstance(item, dict) and item.get("name") == tag]
    if len(matches) > 1:
        raise PackagingError(f"local Ollama tags response has duplicate exact tag entries: {tag}")
    return matches[0] if matches else None


def require_absent_tag(tag: str, api_call: ApiCall) -> None:
    if exact_tag_record(api_call("GET", "/api/tags", None), tag) is not None:
        raise PackagingError(f"Ollama tag already exists and will not be overwritten: {tag}")


def captured_tag_digest(tag: str, api_call: ApiCall) -> str:
    tag_record = exact_tag_record(api_call("GET", "/api/tags", None), tag)
    if tag_record is None:
        raise PackagingError("local Ollama tags response did not include the created exact tag")
    digest = tag_record.get("digest")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        raise PackagingError("local Ollama tags evidence did not include a 64-hex digest")
    return digest


def ollama_tag_evidence(tag: str, digest: str, api_call: ApiCall) -> dict[str, Any]:
    shown = api_call("POST", "/api/show", {"model": tag, "verbose": True})
    details = shown.get("details")
    if not isinstance(details, dict):
        raise PackagingError("local Ollama show evidence did not include details")
    if details.get("quantization_level") != "Q4_K_M":
        raise PackagingError("local Ollama show evidence did not confirm Q4_K_M quantization")
    # These fields are supplied by supported Ollama versions; validate them if present.
    if "format" in details and details["format"] != "gguf":
        raise PackagingError("local Ollama show evidence did not confirm GGUF format")
    if "family" in details and details["family"] != "llama":
        raise PackagingError("local Ollama show evidence did not confirm llama family")
    return {"tag": tag, "digest": digest, "quantization": "Q4_K_M",
            "format": details.get("format"), "family": details.get("family")}


def write_modelfile(path: Path, q4_path: Path) -> None:
    path.write_text(
        f"FROM {q4_path}\nTEMPLATE {{{{ .Prompt }}}}\nPARAMETER num_ctx 2048\nPARAMETER num_gpu 999\n",
        encoding="utf-8", newline="\n")


def package(args: argparse.Namespace, runner: Runner = default_runner,
            api_call: ApiCall = default_api_call, build_id: str | None = None) -> Path:
    converter_python = local_existing_path(args.converter_python, "converter python")
    converter_script = local_existing_path(args.converter_script, "converter script")
    quantizer = local_existing_path(args.quantizer, "quantizer")
    ollama_exe = local_existing_path(args.ollama_exe, "ollama executable")
    merged_dir = local_existing_path(args.merged_dir, "merged dir", directory=True)
    output_dir = new_local_output(args.output_dir)
    if not TAG_PREFIX.fullmatch(args.tag_prefix):
        raise PackagingError("tag prefix must be a closed name:tag prefix without leading dash, whitespace, or controls")
    build_id = secrets.token_hex(16) if build_id is None else build_id
    if not re.fullmatch(r"[0-9a-f]{32}", build_id):
        raise PackagingError("build id must be a 128-bit lowercase hexadecimal value")
    actual_tag = f"{args.tag_prefix}-{build_id}"
    merged_evidence = require_pinned_merged_weight(merged_dir, args.merged_model_sha256)
    # Establish every executable pin before touching either process or loopback API state.
    converter_python_evidence = require_file_pin(converter_python, args.converter_python_sha256, "converter python")
    converter_script_evidence = require_file_pin(converter_script, args.converter_script_sha256, "converter script")
    ollama_exe_evidence = require_file_pin(ollama_exe, args.ollama_exe_sha256, "ollama executable")
    quantizer_bundle = quantizer_bundle_evidence(quantizer, args.quantizer_bundle_sha256)
    staging = output_dir.with_name(output_dir.name + ".tmp")
    if staging.exists():
        raise PackagingError(f"temporary output collision: {staging}")

    # Check first: even an otherwise valid create must never adopt/replace a pre-existing tag.
    require_absent_tag(actual_tag, api_call)
    staging.mkdir()
    active_dir = staging
    created_tag = False
    created_digest: str | None = None
    try:
        bf16 = staging / "airi-bf16.gguf"
        q4 = staging / "airi-q4_k_m.gguf"
        run_checked([str(converter_python), str(converter_script), str(merged_dir),
                     "--outtype", "bf16", "--outfile", str(bf16)], "llama.cpp conversion", runner)
        sha256_and_size(bf16)
        run_checked([str(quantizer), str(bf16), str(q4), "Q4_K_M"], "llama.cpp quantization", runner)
        # The importer needs a final, durable absolute source path.  Promote the
        # completed GGUF pair before generating the Modelfile and evidence.
        staging.replace(output_dir)
        active_dir = output_dir
        bf16 = output_dir / bf16.name
        q4 = output_dir / q4.name
        bf16_evidence = sha256_and_size(bf16)
        q4_evidence = sha256_and_size(q4)
        modelfile = output_dir / "Modelfile"
        write_modelfile(modelfile, q4.resolve())
        modelfile_evidence = sha256_and_size(modelfile)
        # Conversion can take long enough for another local process to create
        # the requested name; check again immediately before the mutating call.
        require_absent_tag(actual_tag, api_call)
        run_checked([str(ollama_exe), "create", actual_tag, "-f", str(modelfile)], "ollama create", runner)
        created_tag = True
        created_digest = captured_tag_digest(actual_tag, api_call)
        tag_evidence = ollama_tag_evidence(actual_tag, created_digest, api_call)
        evidence = {
            "schema_version": 1,
            "tool_hashes": {"converter_python": publishable_file_evidence(converter_python_evidence),
                            "converter_script": publishable_file_evidence(converter_script_evidence),
                            "ollama_exe": publishable_file_evidence(ollama_exe_evidence),
                            "quantizer_bundle": quantizer_bundle},
            "pins": {"converter_python_sha256": args.converter_python_sha256,
                     "converter_script_sha256": args.converter_script_sha256,
                     "quantizer_bundle_sha256": args.quantizer_bundle_sha256,
                     "ollama_exe_sha256": args.ollama_exe_sha256},
            "input": {"merged_model": publishable_file_evidence(merged_evidence)},
            "outputs": {"bf16_gguf": publishable_file_evidence(bf16_evidence),
                        "q4_k_m_gguf": publishable_file_evidence(q4_evidence),
                        "modelfile": publishable_file_evidence(modelfile_evidence)},
            "tag_evidence": tag_evidence,
            "adoption_authorized": False,
            "t3": "pending",
        }
        evidence_tmp = output_dir / "package-evidence.json.tmp"
        evidence_tmp.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        evidence_tmp.replace(output_dir / "package-evidence.json")
        return output_dir / "package-evidence.json"
    except Exception as exc:
        cleanup_error: PackagingError | None = None
        retain_output = False
        if created_tag:
            if created_digest is None:
                retain_output = True
                cleanup_error = PackagingError(f"retained unverified Ollama tag without captured digest: {actual_tag}")
            else:
                try:
                    current = exact_tag_record(api_call("GET", "/api/tags", None), actual_tag)
                    if current is None or current.get("digest") != created_digest:
                        retain_output = True
                        cleanup_error = PackagingError(
                            f"retained unverified Ollama tag with changed or missing digest: {actual_tag}")
                    else:
                        cleanup = runner([str(ollama_exe), "rm", actual_tag])
                        if cleanup.returncode != 0:
                            cleanup_error = PackagingError(
                                f"retained unverified Ollama tag after cleanup failure: {actual_tag} (rm exit {cleanup.returncode})")
                except Exception as cleanup_exc:
                    retain_output = True
                    cleanup_error = PackagingError(
                        f"retained unverified Ollama tag after cleanup exception: {actual_tag}: {cleanup_exc}")
        if active_dir.exists():
            # Keep evidence-capable artifacts when removal of an unverified tag failed.
            if cleanup_error is None and not retain_output:
                shutil.rmtree(active_dir)
        if cleanup_error is not None:
            if active_dir.exists():
                try:
                    (active_dir / "package-evidence.json").write_text(json.dumps({
                        "schema_version": 1, "tag": actual_tag, "adoption_authorized": False,
                        "t3": "blocked", "error": str(exc), "cleanup_error": str(cleanup_error),
                    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                except OSError:
                    pass
            raise cleanup_error from exc
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--converter-python", required=True)
    parser.add_argument("--converter-python-sha256", required=True)
    parser.add_argument("--converter-script", required=True)
    parser.add_argument("--converter-script-sha256", required=True)
    parser.add_argument("--quantizer", required=True)
    parser.add_argument("--quantizer-bundle-sha256", required=True)
    parser.add_argument("--merged-dir", required=True)
    parser.add_argument("--merged-model-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--tag-prefix", required=True)
    parser.add_argument("--ollama-exe", required=True)
    parser.add_argument("--ollama-exe-sha256", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        evidence_path = package(parse_args(argv))
    except PackagingError as exc:
        print(f"package_airi_gguf: {exc}")
        return 2
    print(evidence_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
