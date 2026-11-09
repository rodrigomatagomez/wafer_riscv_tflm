"""A dedicated, bounded, on-disk cache for derived chart artifacts.

This directory holds ONLY regenerable output (PNG/SVG/CSV + a small JSON
manifest per chart), keyed by a content hash of the exact chart
specification. It is never read as a source of truth -- chart_engine.py
always recomputes data_rows/caption/citations from the live Evidence
snapshot on a cache miss; a cache hit only skips the matplotlib render,
never the evidence read.

Bounding: capped at MAX_ENTRIES manifests; when exceeded, the
least-recently-rendered entries (by manifest mtime) are evicted first.
This is a demo-scale cache, not a production CDN -- the cap exists so a
long-running demo session can't accumulate unbounded disk usage, not to
optimize for high request volume.

Path safety: `path_for()` is the only way callers (app.py's download
route) resolve a chart id to a filesystem path. It requires the id to
match the exact hex fingerprint format this module generates and the
extension to be one of a fixed whitelist, and always resolves strictly
inside CACHE_DIR -- there is no way for a request to reach a path outside
this directory.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import chart_engine as ce
from evidence import Evidence

MAX_ENTRIES = 200
_ID_RE = re.compile(r"^[0-9a-f]{12,40}$")
_ALLOWED_EXT = {"png", "svg", "csv"}


def _cache_dir() -> Path:
    import os
    override = os.environ.get("RESULTS_CHAT_CHART_CACHE_DIR")
    if override:
        d = Path(override)
    else:
        d = Path(__file__).resolve().parent.parent / "chart_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _manifest_path(chart_id: str) -> Path:
    return _cache_dir() / f"{chart_id}.json"


def path_for(chart_id: str, ext: str) -> Optional[Path]:
    if not _ID_RE.match(chart_id) or ext not in _ALLOWED_EXT:
        return None
    p = (_cache_dir() / f"{chart_id}.{ext}").resolve()
    cache_root = _cache_dir().resolve()
    if cache_root not in p.parents:
        return None
    return p if p.is_file() else None


def _evict_if_needed():
    manifests = sorted(_cache_dir().glob("*.json"), key=lambda p: p.stat().st_mtime)
    excess = len(manifests) - MAX_ENTRIES
    for m in manifests[:max(excess, 0)]:
        chart_id = m.stem
        for ext in _ALLOWED_EXT:
            f = _cache_dir() / f"{chart_id}.{ext}"
            if f.is_file():
                f.unlink()
        m.unlink(missing_ok=True)


def manifest_by_id(chart_id: str) -> Optional[dict]:
    if not _ID_RE.match(chart_id):
        return None
    p = _manifest_path(chart_id)
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def get_or_render(spec: ce.ChartSpec, ev: Evidence) -> dict:
    chart_id = ce.spec_fingerprint(spec)
    manifest_path = _manifest_path(chart_id)
    if manifest_path.is_file():
        manifest_path.touch()  # refresh LRU position
        return json.loads(manifest_path.read_text())

    result = ce.render(spec, ev)
    png_path = _cache_dir() / f"{chart_id}.png"
    svg_path = _cache_dir() / f"{chart_id}.svg"
    csv_path = _cache_dir() / f"{chart_id}.csv"

    png_meta = {"Title": result.title, "Description": result.caption[:500]}
    result.fig.savefig(png_path, metadata=png_meta)
    result.fig.savefig(svg_path, metadata={"Title": result.title})
    import matplotlib.pyplot as plt
    plt.close(result.fig)

    csv_text = ce.rows_to_csv(result.data_rows)
    provenance_header = "\n".join(f"# {k}: {v}" for k, v in result.provenance.items())
    citation_header = "\n".join(f"# source: {c}" for c in result.citations)
    csv_path.write_text(f"# chart_id: {chart_id}\n{provenance_header}\n{citation_header}\n{csv_text}")

    manifest = {
        "chart_id": chart_id,
        "kind": spec.kind,
        "params": spec.params,
        "lang": spec.lang,
        "title": result.title,
        "caption": result.caption,
        "citations": result.citations,
        "provenance": result.provenance,
        "data_rows": result.data_rows,
        "files": {"png": f"{chart_id}.png", "svg": f"{chart_id}.svg", "csv": f"{chart_id}.csv"},
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    _evict_if_needed()
    return manifest
