"""Static contract checks for the worlds.html WebXR fabric demo."""

from pathlib import Path


def _worlds_html() -> str:
    return (Path(__file__).resolve().parents[2] / "web" / "worlds.html").read_text(
        encoding="utf-8"
    )


def test_worlds_weft_has_immersive_ar_hit_test_session():
    html = _worlds_html()
    assert "requestSession('immersive-ar'" in html
    assert "requiredFeatures: ['hit-test']" in html
    assert "requestHitTestSource({ space: viewerSpace })" in html
    assert "frame.getHitTestResults(hitTestSource)" in html
    assert "AR hit-test anchor" in html


def test_worlds_weft_has_xr_select_and_pinch_zoom_hooks():
    html = _worlds_html()
    assert "session.addEventListener('select'" in html
    assert "openWeftDetail(activeWeftNode(), 'XR select')" in html
    assert "session.addEventListener('squeeze'" in html
    assert "zoomWeftShell(1)" in html
    assert "pinch focus shell" in html


def test_worlds_weft_keeps_canvas_detail_fallback():
    html = _worlds_html()
    compact = " ".join(html.split())
    assert 'id="weft-detail-card"' in html
    assert "canvas fallback active" in html
    assert "canvas.addEventListener('click', onTap)" in compact
    assert "openWeftDetail(best, 'canvas tap')" in html
