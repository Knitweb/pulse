<?php
require __DIR__ . '/_lib.php';
$s = status_local();
$peer = peer_status();
if (is_array($peer)) {
  $s['peer'] = [
    'host' => $peer['host'] ?? 'peer',
    'reachable' => !empty($peer['ok']) && empty($peer['stale']),
    'stale' => !empty($peer['stale']),
    'node_count' => $peer['node_count'] ?? 0,
    'frames_total' => $peer['frames_total'] ?? 0,
    'nodes' => array_map(fn($n)=>['id'=>$n['id']??'?','host'=>$n['host']??($peer['host']??'peer'),
        'last_seen'=>$n['last_seen']??0,'age'=>$n['age']??null,'kind'=>$n['kind']??'node',
        'frames_in'=>$n['frames_in']??0,'frames_out'=>$n['frames_out']??0,'head'=>$n['head']??null],
        $peer['nodes'] ?? []),
  ];
} else {
  $s['peer'] = ['reachable'=>false];
}
jexit($s);
