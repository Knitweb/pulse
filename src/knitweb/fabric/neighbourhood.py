"""Optional neighbourhood-scoped knit visibility.

Some people and agents don't want to share value with random strangers — only
with neighbours.  This module lets a node see **only the knits from its own
geographic cell**, layered on top of the existing geohash machinery
(:mod:`knitweb.fabric.spatial`) and the subscription scope
(:mod:`knitweb.fabric.subscription`).

It is **opt-in**: with no :class:`NeighbourhoodScope` supplied, visibility is
unchanged (you see everything, as before).  When a scope *is* supplied, a record
is visible iff its geohash shares the scope's leading ``precision`` characters
with the viewer's location.  ``include_non_geo`` controls whether knits that
carry no location at all remain visible (default: yes — not everything is
geo-tagged).

This is the visibility primitive behind the "see knits from your buurt and chat
over BitChat/Bluetooth" feature; the Bluetooth transport itself is a separate
seam (``p2p/bluetooth_transport``).
"""

from __future__ import annotations

from dataclasses import dataclass

from .spatial import proximate
from .subscription import in_subscription_scope

GEOHASH_FIELD = "geohash"


@dataclass(frozen=True)
class NeighbourhoodScope:
    """A viewer's geographic visibility window.

    Attributes
    ----------
    origin_geohash:
        The viewer's own geohash (e.g. from ``spatial.geohash(lat, lon)``).
    precision:
        How many leading geohash characters define "the neighbourhood".  Larger
        = smaller cell = stricter.  Must be ``>= 1`` and not exceed the origin
        length.
    include_non_geo:
        When ``True`` (default), records without a geohash stay visible.  When
        ``False``, only located knits inside the cell are shown.
    """

    origin_geohash: str
    precision: int
    include_non_geo: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.origin_geohash, str) or not self.origin_geohash:
            raise ValueError("origin_geohash must be a non-empty string")
        if not isinstance(self.precision, int) or isinstance(self.precision, bool):
            raise TypeError("precision must be int")
        if self.precision < 1:
            raise ValueError("precision must be >= 1")
        if self.precision > len(self.origin_geohash):
            raise ValueError("precision exceeds origin_geohash length")


def record_geohash(record: dict) -> str | None:
    """Extract a record's geohash, or ``None`` if it carries no location."""
    value = record.get(GEOHASH_FIELD)
    if isinstance(value, str) and value:
        return value
    # Some records nest a spatial anchor.
    anchor = record.get("anchor")
    if isinstance(anchor, dict):
        nested = anchor.get(GEOHASH_FIELD)
        if isinstance(nested, str) and nested:
            return nested
    return None


def in_neighbourhood(record: dict, scope: NeighbourhoodScope | None) -> bool:
    """Return ``True`` when *record* is visible under *scope*.

    ``scope=None`` means the feature is off — everything is visible.
    """
    if scope is None:
        return True
    geo = record_geohash(record)
    if geo is None:
        return scope.include_non_geo
    return proximate(scope.origin_geohash, geo, scope.precision)


def visible(
    record: dict,
    *,
    subscription: tuple[str, ...] | None = None,
    neighbourhood: NeighbourhoodScope | None = None,
) -> bool:
    """Combined gate: a record is visible iff it passes *both* filters.

    Either filter is optional; ``None`` means "do not restrict on this axis".
    """
    return in_subscription_scope(record, subscription) and in_neighbourhood(
        record, neighbourhood
    )


def neighbours(
    origin_geohash: str, candidates: list[str], precision: int
) -> list[str]:
    """Return the candidate geohashes that fall in ``origin``'s cell.

    Useful for peer selection — dial only neighbours, not random strangers.
    """
    if precision < 1:
        raise ValueError("precision must be >= 1")
    return [g for g in candidates if proximate(origin_geohash, g, precision)]
