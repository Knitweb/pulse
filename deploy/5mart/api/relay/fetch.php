<?php
/* POST api/relay/fetch — drain queued frames for a mailbox (bounded long-poll).
 * Body: {"mailbox": str, "wait": int seconds}
 * Reply: {"messages": [{"rid": int, "frame": base64}, ...]}
 *
 * Honors the client's `wait` (RelayTransport sends 20) up to RELAY_MAX_WAIT —
 * capped low on purpose: every waiting request pins a PHP worker on shared
 * hosting, and the client tolerates an early empty reply by polling again.
 */
require __DIR__ . '/_lib.php';
handle_options();
relay_init();
$b = read_json_body();
$mailbox = $b['mailbox'] ?? '';
if (!preg_match(MB_NAME_RE, $mailbox)) jexit(['messages'=>[], 'error'=>'bad mailbox'], 400);
$wait = $b['wait'] ?? 0;
if (!is_int($wait) && !is_float($wait)) $wait = 0;
$wait = max(0, min((int)$wait, RELAY_MAX_WAIT));

$path = mb_path($mailbox);
$deadline = microtime(true) + $wait;
$msgs = [];
do {
  if (is_file($path)) {
    $fp = fopen($path, 'c+');
    if ($fp) {
      flock($fp, LOCK_EX);
      $live = mb_partition_lines(stream_get_contents($fp));   // drops expired/corrupt
      if ($live) {
        foreach ($live as $ln) {
          $m = json_decode($ln, true);
          $msgs[] = ['rid'=>$m['rid'] ?? 0, 'frame'=>$m['frame']];
        }
      }
      rewind($fp); ftruncate($fp, 0);   // drain (also clears swept expired lines)
      flock($fp, LOCK_UN); fclose($fp);
    }
  }
  if ($msgs || microtime(true) >= $deadline) break;
  usleep(250000);   // 250 ms between polls; lock never held while sleeping
} while (true);

registry_touch($mailbox, ['polls'=>1, 'frames_out'=>count($msgs), 'kind'=>'mailbox']);
jexit(['messages'=>$msgs]);
