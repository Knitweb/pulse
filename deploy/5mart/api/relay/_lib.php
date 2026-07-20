<?php
/* FinField / Knitweb P2P relay — store-and-forward mailbox + node registry.
 * Implements the pulse relay protocol (knitweb.p2p.relay): a dumb pipe that
 * carries opaque base64 frames between mailboxes, plus a light node registry
 * and cross-host gossip so a browser monitor can show the live network.
 * Pure PHP + flat files (no python on these TransIP hosts).
 *
 * v2 hardening, informed by how the established relay designs handle the same
 * problems (see docs/RELAY_COMPETITIVE_NOTES.md in the pulse repo):
 *   - frames expire (TURN allocations / libp2p relay-v2 reservations expire;
 *     v1 kept undelivered frames forever)
 *   - per-mailbox and global byte budgets with explicit 429 refusals
 *     (libp2p relay-v2 resource limits; protects the shared host's disk)
 *   - bounded long-poll on fetch honoring the client's `wait` (DERP holds the
 *     connection open; v1 ignored `wait`, forcing 1 req/s polling) — capped
 *     LOW because every waiting request pins a PHP worker on shared hosting
 *   - strict base64 validation and CORS preflight (v1 accepted any string
 *     and broke browser preflight)
 */

date_default_timezone_set('UTC');
require __DIR__ . '/_config.php';   // defines RELAY_HOST_ID, RELAY_PEER_STATUS (+ optional overrides)

const RELAY_DATA   = __DIR__ . '/_data';
const MB_DIR       = RELAY_DATA . '/mb';
const NODES_FILE   = RELAY_DATA . '/nodes.json';
const NODE_TTL     = 900;       // seconds a node stays "seen" in status
const MB_NAME_RE   = '/^[A-Za-z0-9._:\-]{1,128}$/';

/* Operational limits — override any of these with define() in _config.php. */
defined('RELAY_MAX_FRAME_B')    || define('RELAY_MAX_FRAME_B', 8388608);      // 8 MiB raw = pulse wire MAX_FRAME_BYTES
defined('RELAY_MAX_QUEUE')      || define('RELAY_MAX_QUEUE', 512);            // frames kept per mailbox
defined('RELAY_FRAME_TTL')      || define('RELAY_FRAME_TTL', 3600);           // undelivered frames expire after 1 h
defined('RELAY_MB_MAX_BYTES')   || define('RELAY_MB_MAX_BYTES', 33554432);    // 32 MiB per mailbox queue file
defined('RELAY_TOTAL_MAX_BYTES')|| define('RELAY_TOTAL_MAX_BYTES', 536870912);// 512 MiB across all queues
defined('RELAY_MAX_WAIT')       || define('RELAY_MAX_WAIT', 8);               // fetch long-poll cap (s) — keep low, each waiter pins a PHP worker

// base64 inflates 3→4; allow the encoded form of a max-size frame plus padding
define('RELAY_MAX_FRAME_B64', intdiv(RELAY_MAX_FRAME_B + 2, 3) * 4 + 8);

function relay_init() {
  foreach ([RELAY_DATA, MB_DIR] as $d) if (!is_dir($d)) @mkdir($d, 0770, true);
  // probabilistic GC (PHP-session style): occasionally unlink whole queue
  // files untouched for longer than the frame TTL — an abandoned mailbox
  // self-cleans instead of holding disk budget forever
  if (mt_rand(1, 50) === 1) {
    $cutoff = time() - RELAY_FRAME_TTL;
    foreach (glob(MB_DIR . '/*.jsonl') ?: [] as $f) {
      if (@filemtime($f) < $cutoff) @unlink($f);
    }
  }
}
function cors_headers() {
  header('Access-Control-Allow-Origin: *');
  header('Access-Control-Allow-Methods: POST, GET, OPTIONS');
  header('Access-Control-Allow-Headers: Content-Type');
}
function handle_options() {
  if (($_SERVER['REQUEST_METHOD'] ?? '') === 'OPTIONS') {
    cors_headers();
    http_response_code(204);
    exit;
  }
}
function jexit($obj, $code = 200) {
  http_response_code($code);
  header('Content-Type: application/json');
  header('Cache-Control: no-store');
  cors_headers();
  echo json_encode($obj);
  exit;
}
function read_json_body() {
  $raw = file_get_contents('php://input');
  if ($raw === '' || $raw === false) return [];
  if (strlen($raw) > RELAY_MAX_FRAME_B64 + 4096) jexit(['ok' => false, 'error' => 'payload too large'], 413);
  $d = json_decode($raw, true);
  return is_array($d) ? $d : [];
}
function b64_frame_valid($frame) {
  if (!is_string($frame) || $frame === '' || strlen($frame) > RELAY_MAX_FRAME_B64) return false;
  $raw = base64_decode($frame, true);
  return $raw !== false && strlen($raw) <= RELAY_MAX_FRAME_B;
}
function mb_path($mailbox) { return MB_DIR . '/' . rawurlencode($mailbox) . '.jsonl'; }

/* Split a queue file's contents into live and expired frame lines. */
function mb_partition_lines($contents) {
  $cutoff = time() - RELAY_FRAME_TTL;
  $live = [];
  foreach (explode("\n", $contents) as $ln) {
    if ($ln === '') continue;
    $m = json_decode($ln, true);
    if (!is_array($m) || !isset($m['frame'])) continue;   // drop corrupt lines
    if (($m['t'] ?? 0) < $cutoff) continue;               // drop expired frames
    $live[] = $ln;
  }
  return $live;
}
function queues_total_bytes() {
  $total = 0;
  foreach (glob(MB_DIR . '/*.jsonl') ?: [] as $f) $total += @filesize($f) ?: 0;
  return $total;
}

/* ---- node registry (who's alive) ---------------------------------------- */
function registry_load() {
  if (!is_file(NODES_FILE)) return [];
  $d = json_decode(@file_get_contents(NODES_FILE), true);
  return is_array($d) ? $d : [];
}
function registry_touch($id, $patch = []) {
  if ($id === '' || $id === null) return;
  $fp = fopen(NODES_FILE, 'c+');
  if (!$fp) return;
  flock($fp, LOCK_EX);
  $raw = stream_get_contents($fp);
  $reg = $raw ? (json_decode($raw, true) ?: []) : [];
  $now = time();
  $n = $reg[$id] ?? ['id' => $id, 'first_seen' => $now, 'frames_in' => 0, 'frames_out' => 0, 'polls' => 0];
  $n['last_seen'] = $now;
  $n['host'] = $n['host'] ?? RELAY_HOST_ID;
  foreach ($patch as $k => $v) {
    if ($k === 'frames_in' || $k === 'frames_out' || $k === 'polls') $n[$k] = ($n[$k] ?? 0) + $v;
    else $n[$k] = $v;
  }
  $reg[$id] = $n;
  // prune long-dead nodes to keep the file small
  foreach ($reg as $k => $v) if (($now - ($v['last_seen'] ?? 0)) > NODE_TTL * 8) unset($reg[$k]);
  rewind($fp); ftruncate($fp, 0);
  fwrite($fp, json_encode($reg));
  flock($fp, LOCK_UN); fclose($fp);
}

/* ---- cross-host gossip: pull the peer's status, cache briefly ----------- */
function peer_status($max_age = 20) {
  if (!defined('RELAY_PEER_STATUS') || !RELAY_PEER_STATUS) return null;
  $cache = RELAY_DATA . '/peer_cache.json';
  if (is_file($cache) && (time() - filemtime($cache)) < $max_age) {
    $d = json_decode(@file_get_contents($cache), true);
    if (is_array($d)) return $d;
  }
  $ctx = stream_context_create(['http' => ['timeout' => 4, 'ignore_errors' => true]]);
  $raw = @file_get_contents(RELAY_PEER_STATUS, false, $ctx);
  if ($raw === false) {
    $d = json_decode(@file_get_contents($cache), true);
    return is_array($d) ? array_merge($d, ['stale' => true]) : ['reachable' => false];
  }
  @file_put_contents($cache, $raw);
  $d = json_decode($raw, true);
  return is_array($d) ? $d : ['reachable' => false];
}

/* ---- status snapshot (local, no peer recursion) ------------------------- */
function status_local() {
  relay_init();
  $reg = registry_load(); $now = time();
  $nodes = []; $frames = 0;
  foreach ($reg as $n) {
    if (($now - ($n['last_seen'] ?? 0)) > NODE_TTL) continue;
    $frames += ($n['frames_in'] ?? 0) + ($n['frames_out'] ?? 0);
    $n['age'] = $now - ($n['last_seen'] ?? $now);
    $nodes[] = $n;
  }
  usort($nodes, fn($a, $b) => ($b['last_seen'] ?? 0) - ($a['last_seen'] ?? 0));
  $mbs = is_dir(MB_DIR) ? count(glob(MB_DIR . '/*.jsonl')) : 0;
  return [
    'host' => RELAY_HOST_ID, 'now' => $now, 'ok' => true,
    'nodes' => $nodes, 'node_count' => count($nodes),
    'mailboxes' => $mbs, 'frames_total' => $frames,
    'queue_bytes' => queues_total_bytes(),
    'limits' => [
      'max_frame_bytes' => RELAY_MAX_FRAME_B, 'max_queue' => RELAY_MAX_QUEUE,
      'frame_ttl_s' => RELAY_FRAME_TTL, 'mb_max_bytes' => RELAY_MB_MAX_BYTES,
      'total_max_bytes' => RELAY_TOTAL_MAX_BYTES, 'max_wait_s' => RELAY_MAX_WAIT,
    ],
    'peer_url' => defined('RELAY_PEER_STATUS') ? RELAY_PEER_STATUS : null,
  ];
}
