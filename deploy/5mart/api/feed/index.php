<?php
/* GET api/feed/<path> — FinField feed mirror (second HTTPS bootstrap origin).
 *
 * NAT'd nodes bootstrap the signed FinField feed over HTTPS from the
 * FinField/feed GitHub repo; this endpoint mirrors that content from
 * raw.githubusercontent.com with a small on-disk cache, so the feed stays
 * fetchable when GitHub is unreachable (stale-while-error) and 5mart.ml is a
 * data-serving node rather than only a frame relay. Mirroring is trust-free:
 * head.json is signed and records are content-addressed, so a mirror cannot
 * forge the feed — clients verify, exactly as with the GitHub origin.
 *
 *   GET api/feed/head.json        (moving pointer — short cache)
 *   GET api/feed/MANIFEST.json
 *   GET api/feed/records-00001.jsonl
 *   GET api/feed/series/<...>
 */

const FEED_UPSTREAM   = 'https://raw.githubusercontent.com/FinField/feed/main/feed/';
const OPS_UPSTREAM    = 'https://raw.githubusercontent.com/FinField/feed/main/ops/';
const FEED_CACHE      = __DIR__ . '/_cache';
const FEED_TTL_HEAD   = 60;       // s — head.json/MANIFEST.json move on publish
const FEED_TTL_STATIC = 600;      // s — record shards append slowly
const FEED_MAX_BYTES  = 16777216; // 16 MiB per mirrored file

header('Access-Control-Allow-Origin: *');

$path = $_GET['p'] ?? '';
if ($path === '' || strlen($path) > 200
    || !preg_match('#^[A-Za-z0-9][A-Za-z0-9._/\-]*$#', $path)
    || str_contains($path, '..')) {
  http_response_code(400);
  header('Content-Type: application/json');
  echo json_encode(['ok' => false, 'error' => 'bad path']);
  exit;
}

// ops/<path> maps to the signed ops feed (relay metrics) next to the main
// data feed; every other path stays on the main feed for full compatibility.
$upstream = FEED_UPSTREAM;
if (str_starts_with($path, 'ops/')) {
  $upstream = OPS_UPSTREAM;
  $path = substr($path, 4);
  if ($path === '') { http_response_code(400); header('Content-Type: application/json'); echo json_encode(['ok'=>false,'error'=>'bad path']); exit; }
}

$ttl = str_ends_with($path, '.json') ? FEED_TTL_HEAD : FEED_TTL_STATIC;
if (!is_dir(FEED_CACHE)) @mkdir(FEED_CACHE, 0770, true);
// cache key on the full upstream URL so feed/head.json and ops/head.json
// (same $path after the prefix strip) can never collide
$cache = FEED_CACHE . '/' . sha1($upstream . $path);

$body = null;
$fresh = is_file($cache) && (time() - filemtime($cache)) < $ttl;
if ($fresh) {
  $body = @file_get_contents($cache);
}
if ($body === null || $body === false) {
  $ctx = stream_context_create(['http' => [
    'timeout' => 8, 'ignore_errors' => true,
    'header' => "User-Agent: knitweb-feed-mirror/1.0\r\n",
  ]]);
  $raw = @file_get_contents($upstream . $path, false, $ctx, 0, FEED_MAX_BYTES + 1);
  $status = 0;
  foreach ($http_response_header ?? [] as $h) {
    if (preg_match('#^HTTP/\S+\s+(\d{3})#', $h, $m)) $status = (int)$m[1];
  }
  if ($raw !== false && $status === 200 && strlen($raw) <= FEED_MAX_BYTES) {
    $body = $raw;
    @file_put_contents($cache . '.tmp', $body);
    @rename($cache . '.tmp', $cache);   // atomic refresh
  } elseif (is_file($cache)) {
    $body = @file_get_contents($cache); // stale-while-error: old beats none
    header('X-Feed-Mirror-Stale: 1');
  } else {
    http_response_code($status === 404 ? 404 : 502);
    header('Content-Type: application/json');
    echo json_encode(['ok' => false, 'error' => $status === 404 ? 'not found' : 'upstream unavailable']);
    exit;
  }
}

header('Content-Type: ' . (str_ends_with($path, '.json') ? 'application/json' : 'application/x-ndjson'));
header('Cache-Control: public, max-age=' . $ttl);
header('X-Feed-Mirror: 5mart.ml');
echo $body;
