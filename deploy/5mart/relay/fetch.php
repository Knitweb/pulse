<?php
/**
 * POST api/relay/fetch — drain queued frames for a mailbox (long-poll).
 *
 * Body: {"mailbox": str, "wait": int seconds}
 * Reply: {"messages": [{"frame": base64 str}, ...]}
 *
 * Polls the mailbox directory every RELAY_POLL_INTERVAL_US until a message
 * appears or `wait` (capped at RELAY_MAX_WAIT_SECONDS) elapses, matching the
 * long-poll semantics RelayTransport._fetch_frames expects.
 */

declare(strict_types=1);
require __DIR__ . '/_common.php';

if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
    relay_error('POST required', 405);
}

$body = relay_read_json_body();
$mailbox = relay_sanitize_mailbox($body['mailbox'] ?? null);

$wait = $body['wait'] ?? 0;
if (!is_int($wait) && !is_float($wait)) {
    $wait = 0;
}
$wait = max(0, min((int) $wait, RELAY_MAX_WAIT_SECONDS));

$dir = relay_mailbox_dir($mailbox, create: true);
$deadline = microtime(true) + $wait;

while (true) {
    relay_gc_mailbox($dir);
    $messages = relay_drain_mailbox($dir);
    if (!empty($messages) || microtime(true) >= $deadline) {
        relay_json_response(['messages' => $messages]);
    }
    usleep(RELAY_POLL_INTERVAL_US);
}

/** @return array<int, array{frame: string}> */
function relay_drain_mailbox(string $dir): array
{
    $entries = @scandir($dir) ?: [];
    sort($entries, SORT_STRING); // filenames are zero-padded-time-prefixed
    $messages = [];
    foreach ($entries as $entry) {
        if ($entry === '.' || $entry === '..' || str_starts_with($entry, '.')) {
            continue;
        }
        $path = $dir . '/' . $entry;
        $raw = @file_get_contents($path);
        @unlink($path);
        if ($raw === false) {
            continue;
        }
        $decoded = json_decode($raw, true);
        if (is_array($decoded) && isset($decoded['frame']) && is_string($decoded['frame'])) {
            $messages[] = ['frame' => $decoded['frame']];
        }
    }
    return $messages;
}
