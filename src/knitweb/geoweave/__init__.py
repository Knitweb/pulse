"""GeoWeave bridge — import PAR (Pulse AR) findings into the fabric.

The GeoWeave repos (`Knitweb/weave-core`, `weave-node`, `weave-client-unity`,
`weave-client-web`) capture the physical world: a Quest 3/3S passthrough frame
or a browser WebGPU frame runs YOLO, and each recognized object becomes a
signed *finding* — canonical JSON, SHA-256 id, Ed25519 signature, a
``did:key`` observer, and an OGC GeoPose for both object and camera.

Pulse speaks a different dialect on purpose: float-free canonical CBOR,
secp256k1 ``pls1`` addresses, geohash cells. This package is the one declared
crossing between the two — verify the foreign envelope first, then re-express
it as a :class:`~knitweb.fabric.observation.FieldObservation` the fabric can
anchor, attest and share.
"""
