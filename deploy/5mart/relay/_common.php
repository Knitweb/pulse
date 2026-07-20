<?php
/**
 * Shared helpers for the store-and-forward relay endpoints.
 *
 * Mirrors the contract implemented by src/knitweb/p2p/relay.py::RelayTransport:
 * a dumb, opaque mailbox. This layer never inspects the carried frame beyond
 * base64/size validation; it only queues and drains bytes per mailbox id.
 *
 * Storage lives OUTSIDE the web docroot (one level above `www/`) so mailbox
 * contents can never be listed or fetched by guessing a static URL.
 */

declare(strict_types=1);

// 8 MiB matches knitweb.p2p.wire.MAX_FRAME_BYTES; base64 inflates by ~4/3, so
// the JSON body itself can run somewhat larger — checked separately below.
const RELAY_MAX_FRAME_BYTES = 8 * 1024 * 1024;
// PHP-FPM/CGI workers on shared hosting have a bounded execution window; cap
// long-poll wait well under a typical 30s host limit regardless of what the
// client asks for.
const RELAY_MAX_WAIT_SECONDS = 25;
const RELAY_POLL_INTERVAL_US = 250000; // 250ms
// A queued message older than this is considered abandoned (peer vanished
// before fetch-ing) and is swept on the next touch of its mailbox.
const RELAY_MESSAGE_TTL_SECONDS = 3600;

function relay_queue_root(): string
{
    // www/api/relay/ -> up three levels -> sibling `relay_queues/` next to `www/`.
    return dirname(__DIR__, 3) . '/relay_queues';
}

function relay_json_response(array $body, int $status = 200): void
{
    http_response_code($status);
    header('Content-Type: application/json');
    header('Cache-Control: no-store');
    echo json_encode($body);
    exit;
}

function relay_error(string $message, int $status = 400): void
{
    relay_json_response(['ok' => false, 'error' => $message], $status);
}

function relay_read_json_body(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === false || $raw === '') {
        relay_error('empty request body');
    }
    if (strlen($raw) > (int) (RELAY_MAX_FRAME_BYTES * 1.4)) {
        relay_error('request body too large');
    }
    $decoded = json_decode($raw, true);
    if (!is_array($decoded)) {
        relay_error('request body must be a JSON object');
    }
    return $decoded;
}

/** Validate + sanitize a mailbox id. Also doubles as a path-traversal guard. */
function relay_sanitize_mailbox(mixed $mailbox): string
{
    if (!is_string($mailbox) || $mailbox === '') {
        relay_error('missing mailbox');
    }
    if (!preg_match('/^[A-Za-z0-9_-]{1,128}$/', $mailbox)) {
        relay_error('invalid mailbox id');
    }
    return $mailbox;
}

function relay_mailbox_dir(string $mailbox, bool $create = false): string
{
    $dir = relay_queue_root() . '/' . $mailbox;
    if ($create && !is_dir($dir)) {
        if (!mkdir($dir, 0700, true) && !is_dir($dir)) {
            relay_error('could not allocate mailbox', 500);
        }
    }
    return $dir;
}

/** Best-effort sweep of a mailbox's stale (TTL-expired) message files. */
function relay_gc_mailbox(string $dir): void
{
    if (!is_dir($dir)) {
        return;
    }
    $cutoff = time() - RELAY_MESSAGE_TTL_SECONDS;
    $entries = @scandir($dir) ?: [];
    foreach ($entries as $entry) {
        if ($entry === '.' || $entry === '..') {
            continue;
        }
        $path = $dir . '/' . $entry;
        $mtime = @filemtime($path);
        if ($mtime !== false && $mtime < $cutoff) {
            @unlink($path);
        }
    }
}
