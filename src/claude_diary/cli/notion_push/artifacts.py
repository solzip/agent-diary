"""Writing each push to a local run directory.

Notion is the destination but not the record: if a push half-fails, or a row
is later edited by hand, the only way back to what was actually submitted is
a local copy. Each run writes the input JSON, the working-tree diff, the
rendered preview and a manifest, and every entry is sha256-stamped so a
reference can be checked against the file it names.
"""

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime

# Named after this tool. It used to be `.codefleet/runs`, borrowed from a
# separate project, which meant installing agent-diary put a directory named
# after unrelated software into your repository. An existing `.codefleet/runs`
# is still honoured so nobody's history splits across two folders mid-stream.
ARTIFACT_DIR = ".agent-diary/runs"
LEGACY_ARTIFACT_DIR = ".codefleet/runs"


def default_artifact_dir(cwd: str) -> str:
    """Where run artifacts go when `--artifact-dir` was not given."""
    legacy = os.path.join(cwd, *LEGACY_ARTIFACT_DIR.split("/"))
    if os.path.isdir(legacy):
        return LEGACY_ARTIFACT_DIR
    return ARTIFACT_DIR


def _prepare_run_artifacts(input_path, data, tasks, session_id, date_str, cwd, artifact_dir):
    if not artifact_dir:
        return None
    run_id = _run_id(session_id, date_str)
    run_dir = os.path.abspath(os.path.join(cwd, artifact_dir, run_id))
    os.makedirs(run_dir, exist_ok=True)
    artifacts = {
        "run_id": run_id,
        "run_dir": run_dir,
        "cwd": cwd,
        "refs": [],
    }
    if input_path and os.path.exists(input_path):
        input_copy = os.path.join(run_dir, "input.json")
        shutil.copyfile(input_path, input_copy)
        artifacts["refs"].append(_artifact_ref(cwd, input_copy, "input", "original diary-notion JSON input"))
    diff_path = os.path.join(run_dir, "git-diff.patch")
    diff_text = _git_diff(cwd)
    _write_text_file(diff_path, diff_text)
    artifacts["refs"].append(_artifact_ref(cwd, diff_path, "diff", "git diff at diary-notion push time"))
    return artifacts


def _write_artifact_preview(run_artifacts, preview):
    path = os.path.join(run_artifacts["run_dir"], "preview.md")
    _write_text_file(path, preview)
    run_artifacts["refs"] = [
        ref for ref in run_artifacts["refs"] if ref.get("kind") != "preview"
    ]
    run_artifacts["refs"].append(_artifact_ref(
        run_artifacts["cwd"], path, "preview", "rendered Notion body preview"
    ))


def _finalize_artifact_manifest(run_artifacts, tasks, results=None):
    manifest_path = os.path.join(run_artifacts["run_dir"], "manifest.json")
    manifest = {
        "run_id": run_artifacts["run_id"],
        "tasks": [task.get("title") or "(untitled)" for task in tasks],
        "artifacts": run_artifacts["refs"],
    }
    if results is not None:
        manifest["results"] = {
            "pushed": len(results.get("pushed") or []),
            "skipped": len(results.get("skipped") or []),
            "failed": len(results.get("failed") or []),
        }
    _write_text_file(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
    run_artifacts["refs"] = [
        ref for ref in run_artifacts["refs"] if ref.get("kind") != "manifest"
    ]
    run_artifacts["refs"].append(_artifact_ref(
        run_artifacts["cwd"], manifest_path, "manifest", "local run artifact manifest"
    ))


def _set_run_artifacts(tasks, run_artifacts):
    refs = run_artifacts.get("refs") or []
    ref_keys = {(ref.get("kind"), ref.get("path")) for ref in refs}
    for task in tasks:
        appendix = task.setdefault("appendix", {})
        existing = appendix.get("artifacts") or []
        if isinstance(existing, dict):
            existing = [existing]
        elif not isinstance(existing, list):
            existing = []
        cleaned = []
        for item in existing:
            if isinstance(item, dict) and (item.get("kind"), item.get("path")) in ref_keys:
                continue
            cleaned.append(item)
        appendix["artifacts"] = cleaned + refs


def _artifact_ref(cwd, path, kind, summary):
    return {
        "kind": kind,
        "path": _relpath(cwd, path),
        "summary": summary,
        "sha256": _sha256_file(path),
    }


def _run_id(session_id, date_str):
    stamp = datetime.now().strftime("%H%M%S")
    safe_session = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(session_id or "run"))
    return "%s-%s-%s" % (date_str.replace("-", ""), stamp, safe_session[:24])


def _git_diff(cwd):
    try:
        result = subprocess.run(
            ["git", "-c", "safe.directory=%s" % cwd.replace("\\", "/"), "diff", "--binary"],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except Exception as e:
        return "git diff unavailable: %s\n" % e
    if result.returncode != 0:
        return "git diff failed: %s\n" % (result.stderr or result.stdout)
    return result.stdout or "No working tree diff at capture time.\n"


def _write_text_file(path, text):
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _relpath(cwd, path):
    try:
        return os.path.relpath(path, cwd).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")
