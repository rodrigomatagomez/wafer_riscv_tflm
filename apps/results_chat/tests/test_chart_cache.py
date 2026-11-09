import chart_cache
import chart_engine as ce


def test_get_or_render_creates_files(ev, chart_cache_dir):
    spec = ce.validate_spec({"kind": "f1_by_class"})
    manifest = chart_cache.get_or_render(spec, ev)
    chart_id = manifest["chart_id"]
    for ext in ("png", "svg", "csv"):
        p = chart_cache_dir / f"{chart_id}.{ext}"
        assert p.is_file(), f"missing {p}"
    assert (chart_cache_dir / f"{chart_id}.json").is_file()


def test_get_or_render_is_cached_on_second_call(ev, chart_cache_dir):
    spec = ce.validate_spec({"kind": "f1_by_class"})
    m1 = chart_cache.get_or_render(spec, ev)
    png_path = chart_cache_dir / f"{m1['chart_id']}.png"
    mtime1 = png_path.stat().st_mtime
    m2 = chart_cache.get_or_render(spec, ev)
    mtime2 = png_path.stat().st_mtime
    assert m1 == m2
    assert mtime1 == mtime2  # not re-rendered


def test_path_for_resolves_existing_file(ev, chart_cache_dir):
    spec = ce.validate_spec({"kind": "memory_budget"})
    manifest = chart_cache.get_or_render(spec, ev)
    p = chart_cache.path_for(manifest["chart_id"], "png")
    assert p is not None and p.is_file()


def test_path_for_rejects_path_traversal(chart_cache_dir):
    assert chart_cache.path_for("../../../etc/passwd", "png") is None
    assert chart_cache.path_for("..%2f..%2fetc%2fpasswd", "png") is None


def test_path_for_rejects_bad_extension(ev, chart_cache_dir):
    spec = ce.validate_spec({"kind": "memory_budget"})
    manifest = chart_cache.get_or_render(spec, ev)
    assert chart_cache.path_for(manifest["chart_id"], "py") is None
    assert chart_cache.path_for(manifest["chart_id"], "sh") is None


def test_path_for_rejects_nonexistent_id(chart_cache_dir):
    assert chart_cache.path_for("0" * 20, "png") is None


def test_path_for_rejects_malformed_id(chart_cache_dir):
    assert chart_cache.path_for("not-hex-!!", "png") is None
    assert chart_cache.path_for("", "png") is None


def test_manifest_by_id_roundtrip(ev, chart_cache_dir):
    spec = ce.validate_spec({"kind": "invoke_cycles"})
    manifest = chart_cache.get_or_render(spec, ev)
    fetched = chart_cache.manifest_by_id(manifest["chart_id"])
    assert fetched == manifest


def test_manifest_by_id_unknown_returns_none(chart_cache_dir):
    assert chart_cache.manifest_by_id("0" * 20) is None


def test_eviction_bounds_cache_size(ev, chart_cache_dir, monkeypatch):
    monkeypatch.setattr(chart_cache, "MAX_ENTRIES", 2)
    specs = [
        {"kind": "case_scores", "params": {"case_id": i}} for i in range(5)
    ]
    for raw in specs:
        chart_cache.get_or_render(ce.validate_spec(raw), ev)
    manifests = list(chart_cache_dir.glob("*.json"))
    assert len(manifests) <= 2


def test_csv_export_contains_provenance_header(ev, chart_cache_dir):
    spec = ce.validate_spec({"kind": "confusion_matrix", "params": {"normalize": True, "model_tag": "A"}})
    manifest = chart_cache.get_or_render(spec, ev)
    csv_path = chart_cache_dir / f"{manifest['chart_id']}.csv"
    text = csv_path.read_text()
    assert "chart_id" in text
    assert "normalize" in text
    assert "model_tag: A" in text
    assert "source:" in text
