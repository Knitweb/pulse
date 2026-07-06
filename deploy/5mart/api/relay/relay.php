<?php
/**
 * relay.php — Knitweb store-and-forward mailbox relay (de "geavanceerde poort" op 5mart.ml).
 *
 * Bridget NAT/firewalled nodes én browser/lokale light-nodes op één P2P-net:
 *   POST api/relay/send   { "mailbox": <id>, "rid": <int>, "frame": <base64> }  -> { "ok": true }
 *   POST api/relay/fetch  { "mailbox": <id>, "wait": <sec> }  -> { "messages": [ { "frame": <base64> }, ... ] }
 *
 * Protocol exact volgens knitweb.p2p.relay (RelayTransport). Frames zijn opaak
 * (base64) — de relay leest of interpreteert ze nooit. Dependency-vrij PHP; werkt
 * op gewone shared hosting (TransIP). CORS aan zodat knitweb.art / 5mart.ml /
 * lokale testers als node kunnen meedoen.
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Cache-Control: no-store');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }
if ($_SERVER['REQUEST_METHOD'] !== 'POST')    { http_response_code(405); echo json_encode(['ok' => false, 'error' => 'POST only']); exit; }

$action = isset($_GET['action']) ? $_GET['action'] : '';
$raw    = file_get_contents('php://input');
if (strlen($raw) > 4000000) { echo json_encode(['ok' => false, 'error' => 'payload too large']); exit; }
$body   = json_decode($raw, true);
if (!is_array($body)) { echo json_encode(['ok' => false, 'error' => 'bad json']); exit; }

// Mailbox-opslag buiten de webroot-inhoud; per mailbox één append-only queue-bestand.
$DATA = __DIR__ . '/_mailboxes';
if (!is_dir($DATA)) { @mkdir($DATA, 0700, true); }

/** Veilig pad voor een mailbox-id ([a-zA-Z0-9_-], max 128). */
function mbox_path($dir, $mailbox) {
    $safe = preg_replace('/[^a-zA-Z0-9_-]/', '', (string)$mailbox);
    if ($safe === '' || strlen($safe) > 128) { return null; }
    return $dir . '/' . $safe . '.q';
}

/** Drain (lees + wis) alle frames voor een mailbox onder exclusieve lock. */
function drain($path) {
    if (!file_exists($path)) { return array(); }
    $fp = fopen($path, 'c+');
    if (!$fp) { return array(); }
    $out = array();
    if (flock($fp, LOCK_EX)) {
        rewind($fp);
        while (($line = fgets($fp)) !== false) {
            $m = json_decode(trim($line), true);
            if (is_array($m) && isset($m['frame']) && is_string($m['frame'])) {
                $out[] = array('frame' => $m['frame']);
            }
        }
        ftruncate($fp, 0);          // frames zijn geconsumeerd
        flock($fp, LOCK_UN);
    }
    fclose($fp);
    return $out;
}

if ($action === 'send') {
    $path = mbox_path($DATA, isset($body['mailbox']) ? $body['mailbox'] : '');
    if ($path === null) { echo json_encode(['ok' => false, 'error' => 'bad mailbox']); exit; }
    $frame = isset($body['frame']) ? $body['frame'] : '';
    if (!is_string($frame) || $frame === '' || strlen($frame) > 3000000) {
        echo json_encode(['ok' => false, 'error' => 'bad frame']); exit;
    }
    $fp = fopen($path, 'ab');
    if (!$fp) { echo json_encode(['ok' => false, 'error' => 'store unavailable']); exit; }
    if (flock($fp, LOCK_EX)) {
        fwrite($fp, json_encode(array('frame' => $frame)) . "\n");
        flock($fp, LOCK_UN);
    }
    fclose($fp);
    echo json_encode(['ok' => true]);
    exit;
}

if ($action === 'fetch') {
    $path = mbox_path($DATA, isset($body['mailbox']) ? $body['mailbox'] : '');
    if ($path === null) { echo json_encode(['messages' => array()]); exit; }
    $wait = isset($body['wait']) ? intval($body['wait']) : 0;
    if ($wait < 0) { $wait = 0; } if ($wait > 25) { $wait = 25; }   // begrensde long-poll
    $deadline = microtime(true) + $wait;
    do {
        $messages = drain($path);
        if (!empty($messages) || microtime(true) >= $deadline) { break; }
        usleep(400000);            // 0,4 s tussen polls; lock niet vastgehouden
    } while (true);
    echo json_encode(['messages' => $messages]);
    exit;
}

http_response_code(404);
echo json_encode(['ok' => false, 'error' => 'unknown action']);
