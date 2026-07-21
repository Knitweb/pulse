"""Label maps — turn woven knowledge into recognition targets.

The scene-semantic recognition path (:class:`~knitweb.edge.recognize.SceneSemanticBackend`)
and the GeoWeave bridge (:func:`knitweb.geoweave.bridge.finding_to_observation`)
both need the same table: *detector label → Web node CID*. This module builds
that table from the Web itself, so anything already woven — a MOLGANG molecule,
a chemistry apparatus node, a supply-chain asset — becomes a recognizable
physical target without any separate registry.

The convention is deliberately minimal: a knowledge node is recognizable iff it
carries a ``title`` (the detector label) — e.g. the ``leaching_pot`` nodes the
chemistry knitweb already weaves. Class-level confidence is supplied by the
caller as an integer in milli-units and converted to the backend's float at
this one declared boundary (edge-side only; nothing here is woven or hashed).
"""

from __future__ import annotations

__all__ = ["target_map_from_web", "label_map_from_web"]

_DEFAULT_KINDS = ("knowledge",)


def target_map_from_web(
    web,
    *,
    kinds: tuple[str, ...] = _DEFAULT_KINDS,
    title_field: str = "title",
) -> dict[str, str]:
    """``label -> CID`` for every titled knowledge node woven into ``web``.

    When several nodes share a title, the lexicographically smallest CID wins —
    deterministic on every peer, no wall clock, no ordering dependence.
    """
    out: dict[str, str] = {}
    for cid, record in web.nodes.items():
        if not isinstance(record, dict) or record.get("kind") not in kinds:
            continue
        label = record.get(title_field)
        if not isinstance(label, str) or not label:
            continue
        if label not in out or cid < out[label]:
            out[label] = cid
    return out


def label_map_from_web(
    web,
    *,
    kinds: tuple[str, ...] = _DEFAULT_KINDS,
    title_field: str = "title",
    class_confidence_milli: int = 900,
) -> dict[str, tuple[str, float]]:
    """A ready :class:`SceneSemanticBackend` table from woven knowledge.

    ``class_confidence_milli`` is the class-level reliability (integer,
    0–1000); it becomes the backend's float here, edge-side, at this one
    declared boundary. Anything below 1000 keeps the confirmation gate on —
    which is exactly right for detector-driven recognition.
    """
    if isinstance(class_confidence_milli, bool) or not isinstance(class_confidence_milli, int):
        raise TypeError("class_confidence_milli must be an integer")
    if not 0 <= class_confidence_milli <= 1000:
        raise ValueError("class_confidence_milli must be in [0, 1000]")
    confidence = class_confidence_milli / 1000
    return {
        label: (cid, confidence)
        for label, cid in target_map_from_web(
            web, kinds=kinds, title_field=title_field
        ).items()
    }
