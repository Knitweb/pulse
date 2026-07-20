<?php
/* POST api/relay/send — deposit one opaque frame into a named mailbox.
 * Body: {"mailbox": str, "rid": int, "frame": base64}
 * Reply: {"ok": true} | {"ok": false, "error": str}  (429 when a budget refuses)
 */
require __DIR__ . '/_lib.php';
handle_options();
relay_init();
$b = read_json_body();
$mailbox = $b['mailbox'] ?? '';
$frame   = $b['frame'] ?? '';
$rid     = $b['rid'] ?? 0;
if (!preg_match(MB_NAME_RE, $mailbox)) jexit(['ok'=>false,'error'=>'bad mailbox'], 400);
if (!b64_frame_valid($frame)) jexit(['ok'=>false,'error'=>'bad frame'], 400);

$path = mb_path($mailbox);
$entry = json_encode(['rid'=>$rid,'frame'=>$frame,'t'=>time()]);

// Budget refusals BEFORE taking the write lock (libp2p relay-v2 style limits):
// an over-budget sender gets an explicit 429 and can fall back to another path.
$mb_size = is_file($path) ? (@filesize($path) ?: 0) : 0;
if ($mb_size + strlen($entry) > RELAY_MB_MAX_BYTES) jexit(['ok'=>false,'error'=>'mailbox full'], 429);
if (queues_total_bytes() + strlen($entry) > RELAY_TOTAL_MAX_BYTES) jexit(['ok'=>false,'error'=>'relay full'], 429);

$fp = fopen($path, 'c+'); if (!$fp) jexit(['ok'=>false,'error'=>'store'], 500);
flock($fp, LOCK_EX);
$lines = mb_partition_lines(stream_get_contents($fp));   // drops expired/corrupt
$lines[] = $entry;
if (count($lines) > RELAY_MAX_QUEUE) $lines = array_slice($lines, -RELAY_MAX_QUEUE);
rewind($fp); ftruncate($fp, 0); fwrite($fp, implode("\n", $lines) . "\n");
flock($fp, LOCK_UN); fclose($fp);
registry_touch($mailbox, ['frames_in'=>1, 'kind'=>'mailbox']);
if (!empty($b['from']) && is_string($b['from']) && preg_match(MB_NAME_RE, $b['from'])) {
  registry_touch($b['from'], ['frames_out'=>1]);
}
jexit(['ok'=>true]);
