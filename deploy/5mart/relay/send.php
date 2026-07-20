<?php
/**
 * POST api/relay/send — deposit one opaque frame into a named mailbox.
 *
 * Body: {"mailbox": str, "rid": int, "frame": base64 str}
 * Reply: {"ok": true} | {"ok": false, "error": str}
 *
 * The frame is never decoded here — only base64-validated and size-capped —
 * matching the "dumb pipe" contract in src/knitweb/p2p/relay.py.
 */

declare(strict_types=1);
require __DIR__ . '/_common.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    relay_error('POST required', 405);
}

$body = relay_read_json_body();
$mailbox = relay_sanitize_mailbox($body['mailbox'] ?? null);

$frameB64 = $body['frame'] ?? null;
if (!is_string($frameB64) || $frameB64 === '') {
    relay_error('missing frame');
}
$frame = base64_decode($frameB64, true);
if ($frame === false) {
    relay_error('frame is not valid base64');
}
if (strlen($frame) > RELAY_MAX_FRAME_BYTES) {
    relay_error('frame exceeds maximum size');
}

$rid = $body['rid'] ?? null;
if (!is_int($rid)) {
    // Kept permissive: rid is opaque correlation state to the relay, not
    // something we act on — but it must round-trip as JSON-safe.
    $rid = 0;
}

$dir = relay_mailbox_dir($mailbox, create: true);
relay_gc_mailbox($dir);

// Store the already-base64 frame verbatim so fetch can hand it straight back
// without a decode/re-encode round trip. Filename = time-ordered + random
// suffix so concurrent senders never collide; write-then-rename is atomic.
$name = sprintf('%020.6f-%s.json', microtime(true), bin2hex(random_bytes(8)));
$tmp = $dir . '/.' . $name . '.tmp';
$final = $dir . '/' . $name;

$payload = json_encode(['frame' => $frameB64, 'rid' => $rid]);
if (file_put_contents($tmp, $payload, LOCK_EX) === false) {
    relay_error('could not queue message', 500);
}
if (!rename($tmp, $final)) {
    @unlink($tmp);
    relay_error('could not queue message', 500);
}

relay_json_response(['ok' => true]);
