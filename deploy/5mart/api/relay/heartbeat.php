<?php
require __DIR__ . '/_lib.php';
relay_init();
// host node: a fresh rolling head each beat, proving liveness
$prev = registry_load()['host:' . RELAY_HOST_ID]['head'] ?? str_repeat('0', 16);
$head = substr(hash('sha256', $prev . '|' . time() . '|' . RELAY_HOST_ID), 0, 16);
registry_touch('host:' . RELAY_HOST_ID, ['kind'=>'host', 'head'=>$head, 'role'=>'relay+node', 'frames_in'=>1]);
// gossip: warm the peer-status cache (pull), and merge peer host-node into our registry
$peer = peer_status(0);
if (is_array($peer) && !empty($peer['nodes'])) {
  foreach ($peer['nodes'] as $n) {
    if (($n['kind'] ?? '') === 'host' && !empty($n['id'])) {
      registry_touch((string)$n['id'], ['kind'=>'host', 'head'=>$n['head']??null, 'via'=>'gossip', 'host'=>$n['host']??'peer']);
    }
  }
}
jexit(['ok'=>true, 'host'=>RELAY_HOST_ID, 'head'=>$head]);
