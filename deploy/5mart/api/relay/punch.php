<?php
/* POST api/relay/punch — hole-punch rendezvous (the production Rendezvous
 * behind knitweb.p2p.holepunch.HolePunchTransport).
 *
 * One endpoint, action in the JSON body (mirrors the mailbox API's shape):
 *   {"action":"whoami"}                       -> {"ok":true,"host":ip,"port":p}
 *   {"action":"register","punch_id":s,"port":n} -> {"ok":true}
 *   {"action":"resolve","punch_id":s}         -> {"ok":true,"endpoint":{"host","port"}|null}
 *   {"action":"unregister","punch_id":s}      -> {"ok":true}
 *
 * BitTorrent-tracker model: the public HOST is always server-observed
 * (REMOTE_ADDR — unspoofable), the PORT is what the listener declares it
 * bound (correct for the port-preserving/EIM NATs home connections use;
 * a symmetric NAT yields an undialable endpoint, which the client treats
 * as a failed punch and falls back to the relay mailbox).
 *
 * Anti-hijack: an entry may only be overwritten or unregistered from the
 * IP that registered it, until it expires (PUNCH_TTL). Entries are
 * ephemeral by design — a punched endpoint is only meaningful while the
 * listener is up, so the TTL is short and re-registration is the refresh.
 */
require __DIR__ . '/_lib.php';
handle_options();
relay_init();

defined('RELAY_PUNCH_TTL') || define('RELAY_PUNCH_TTL', 300);   // s before an entry expires
defined('RELAY_PUNCH_MAX') || define('RELAY_PUNCH_MAX', 4096);  // registry size cap

const PUNCH_FILE = RELAY_DATA . '/punch.json';

$b = read_json_body();
$action = $b['action'] ?? '';
$caller = $_SERVER['REMOTE_ADDR'] ?? '';

if ($action === 'whoami') {
  jexit(['ok'=>true, 'host'=>$caller, 'port'=>(int)($_SERVER['REMOTE_PORT'] ?? 0)]);
}

if (!in_array($action, ['register','resolve','unregister'], true)) {
  jexit(['ok'=>false,'error'=>'unknown action'], 400);
}
$punch_id = $b['punch_id'] ?? '';
if (!preg_match(MB_NAME_RE, $punch_id)) jexit(['ok'=>false,'error'=>'bad punch_id'], 400);

$fp = fopen(PUNCH_FILE, 'c+');
if (!$fp) jexit(['ok'=>false,'error'=>'store'], 500);
flock($fp, LOCK_EX);
$reg = json_decode(stream_get_contents($fp), true) ?: [];
$now = time();
foreach ($reg as $k => $v) if (($now - ($v['t'] ?? 0)) > RELAY_PUNCH_TTL) unset($reg[$k]);

$out = ['ok'=>true];
if ($action === 'register') {
  $port = $b['port'] ?? 0;
  if (!is_int($port) || $port < 1 || $port > 65535) { flock($fp, LOCK_UN); fclose($fp); jexit(['ok'=>false,'error'=>'bad port'], 400); }
  $cur = $reg[$punch_id] ?? null;
  if ($cur !== null && ($cur['by'] ?? '') !== $caller) { flock($fp, LOCK_UN); fclose($fp); jexit(['ok'=>false,'error'=>'punch_id taken'], 409); }
  if ($cur === null && count($reg) >= RELAY_PUNCH_MAX) { flock($fp, LOCK_UN); fclose($fp); jexit(['ok'=>false,'error'=>'rendezvous full'], 429); }
  $reg[$punch_id] = ['host'=>$caller, 'port'=>$port, 'by'=>$caller, 't'=>$now];
} elseif ($action === 'resolve') {
  $e = $reg[$punch_id] ?? null;
  $out['endpoint'] = $e ? ['host'=>$e['host'], 'port'=>$e['port']] : null;
} else { // unregister — idempotent, owner-only while the entry is live
  $cur = $reg[$punch_id] ?? null;
  if ($cur !== null && ($cur['by'] ?? '') === $caller) unset($reg[$punch_id]);
}

rewind($fp); ftruncate($fp, 0); fwrite($fp, json_encode($reg));
flock($fp, LOCK_UN); fclose($fp);
if ($action === 'register') registry_touch('punch:' . $punch_id, ['kind'=>'punch']);
jexit($out);
