"""WNW specify-before-retrieve contracts and BC2 capsules."""

from html.parser import HTMLParser
from pathlib import Path

from knitweb.core import canonical, crypto
from knitweb.wnw import (
    ACCEPT_OPTIONS,
    FactPlanner,
    classify_domain,
    estimate,
    pack,
    unpack,
)


class _AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attr_map = dict(attrs)
        href = attr_map.get("href")
        if href:
            self.hrefs.append(href)


def test_local_dutch_and_english_terms_classify_to_same_domain():
    assert classify_domain("give me all steel mines") == "steel-mines"
    assert classify_domain("alle staal mijnen met detailkaarten") == "steel-mines"


def test_fact_contract_is_deterministic_and_content_addressed():
    a = estimate("give me all steel mines with detail cards", "world", beat=42)
    b = estimate("Give me all steel mines with detail cards", "world", beat=42)
    assert a.to_record() == b.to_record()
    assert a.cid == b.cid
    assert a.cid == canonical.cid(a.to_record())
    assert a.accept_options == ACCEPT_OPTIONS
    assert a.source_layer == "narrow-web"
    assert a.estimated_rows == 9_840
    assert a.byte_budget == 9_840 * 468


def test_scope_factors_are_integer_and_cached_by_beat():
    planner = FactPlanner()
    world = planner.estimate("steel mines", "world", beat=7)
    mesh = planner.estimate("steel mines", "mesh", beat=7)
    nearby = planner.estimate("steel mines", "nearby", beat=7)
    assert mesh.estimated_rows == (world.estimated_rows * 1_800 + 9_999) // 10_000
    assert nearby.estimated_rows == (world.estimated_rows * 300 + 9_999) // 10_000
    assert planner.estimate("steel mines", "mesh", beat=7) is mesh
    assert planner.estimate("steel mines", "mesh", beat=8) is not mesh


def test_cold_start_registry_uses_generic_defaults():
    contract = estimate("unmapped rare words", "nearby", beat=0, registry={})
    assert contract.domain == "generic-facts"
    assert contract.columns == ("entity_id", "label", "kind", "scope", "source_cid", "updated_beat")
    assert contract.estimated_rows == 4


def test_fact_contract_can_be_signed_and_verified():
    priv, _ = crypto.generate_keypair()
    signed = estimate("quantum circuit qasm", "mesh", beat=3).sign(priv)
    assert signed.verify()
    record = signed.to_record()
    assert record["proposal_cid"] == signed.contract.cid
    assert record["signature"] == signed.signature


def test_bc2_capsule_is_two_ascii_lines_and_round_trips_visible_fields():
    contract = estimate("steel mines", "mesh", beat=11)
    capsule = pack(contract)
    lines = capsule.as_lines()
    assert len(lines) == 2
    assert all(len(line) <= 140 for line in lines)
    for line in lines:
        line.encode("ascii")
    assert lines[0] == (
        f"WNW1 steel-mines rows={contract.estimated_rows} "
        f"cols={len(contract.columns)} bytes={contract.byte_budget} beat=11"
    )
    assert lines[1] == (
        f"CID? est={contract.estimate_digest} scope=mesh accept=narrow/refine/query"
    )
    parsed = unpack(capsule)
    assert parsed["domain"] == "steel-mines"
    assert parsed["rows"] == contract.estimated_rows
    assert parsed["cols"] == len(contract.columns)
    assert parsed["scope"] == "mesh"


def test_web_folder_exposes_pulse_github_io_root():
    root = Path(__file__).resolve().parents[2]
    index = root / "web" / "index.html"
    assert index.is_file()
    html = index.read_text(encoding="utf-8")
    parser = _AnchorParser()
    parser.feed(html)
    hrefs = set(parser.hrefs)
    assert "worlds.html#specify" in hrefs
    assert "docs/worlds-narrow-web.html" in hrefs
    assert "https://github.com/Knitweb/pulse" in hrefs
