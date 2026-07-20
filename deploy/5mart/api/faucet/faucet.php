<?php
/**
 * faucet.php — dual-coin launch faucet with per-country caps and a waitlist.
 *
 * Two faucets (PLS and PAR), each capped at 150 granted places per country;
 * every later entrant joins a FIFO waitlist. Zero PII: only (address, country
 * code, timestamp) is stored; the client IP is used solely as a salted hash
 * for rate limiting and never written in clear.
 *
 *   POST api/faucet/claim   { "faucet": "pls"|"par", "address": "pls1…", "country": "NL" }
 *       -> { "ok": true, "status": "granted"|"waitlist", "position": <int>, "cap": 150 }
 *   GET  api/faucet/status?faucet=pls&country=NL
 *       -> { "ok": true, "granted": <int>, "cap": 150, "waitlist": <int> }
 *   GET  api/faucet/health  -> { "ok": true, "service": "knitweb-faucet", ... }
 *
 * The faucet records only *reservations*. Actual coin delivery is settled
 * on-ledger by the treasury against these records (docs/DUAL_COIN_IPO_PLAN.md
 * §8): no premine — faucet value is worked value, throttled to spread it.
 * Dependency-free PHP, shared-hosting friendly (TransIP), same conventions as
 * the relay next door (relay.php, issue #337).
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Cache-Control: no-store');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

const CAP_PER_COUNTRY = 150;
const FAUCETS = array('pls', 'par');
const MAX_CLAIMS_PER_IP_DAY = 10;

$DATA = __DIR__ . '/_state';

function fail($code, $msg) { http_response_code($code); echo json_encode(['ok' => false, 'error' => $msg]); exit; }

// Action: ?action= (query-style) or the last path segment (extensionless paths
// /api/faucet/{claim,status,health}, rewritten here by .htaccess).
$action = isset($_GET['action']) ? $_GET['action'] : '';
if ($action === '') {
    $path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
    $tail = basename((string)$path);
    if (in_array($tail, array('claim', 'status', 'health'), true)) { $action = $tail; }
}

if ($action === 'health') {
    echo json_encode(['ok' => true, 'service' => 'knitweb-faucet', 'faucets' => FAUCETS,
                      'cap_per_country' => CAP_PER_COUNTRY, 'time' => time()]);
    exit;
}

// ---- input ---------------------------------------------------------------
if ($action === 'claim') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') { fail(405, 'POST only'); }
    $body = json_decode((string)file_get_contents('php://input'), true);
    if (!is_array($body)) { fail(400, 'invalid JSON'); }
    $faucet  = isset($body['faucet'])  ? strtolower(trim((string)$body['faucet']))  : '';
    $address = isset($body['address']) ? trim((string)$body['address'])             : '';
    $country = isset($body['country']) ? strtoupper(trim((string)$body['country'])) : '';
} else if ($action === 'status') {
    $faucet  = isset($_GET['faucet'])  ? strtolower(trim((string)$_GET['faucet']))  : '';
    $country = isset($_GET['country']) ? strtoupper(trim((string)$_GET['country'])) : '';
    $address = '';
} else {
    fail(404, 'unknown action');
}

if (!in_array($faucet, FAUCETS, true))            { fail(400, 'faucet must be pls or par'); }
if (!preg_match('/^[A-Z]{2}$/', $country))        { fail(400, 'country must be a 2-letter ISO code'); }
// pls1 + base32(scheme byte || sha256^2(pubkey)[:20]) — permissive length window.
if ($action === 'claim' && !preg_match('/^pls1[a-z2-7]{20,64}$/', $address)) {
    fail(400, 'address must be a pls1 base32 address');
}

// ---- storage: one JSONL ledger per (faucet, country), guarded by flock ----
$dir = $DATA . '/' . $faucet;
if (!is_dir($dir) && !mkdir($dir, 0770, true) && !is_dir($dir)) { fail(500, 'storage unavailable'); }
$ledger = $dir . '/' . $country . '.jsonl';

$fh = fopen($ledger, 'c+');
if ($fh === false) { fail(500, 'storage unavailable'); }
if (!flock($fh, LOCK_EX)) { fclose($fh); fail(503, 'busy, retry'); }

$entries = array();
rewind($fh);
while (($line = fgets($fh)) !== false) {
    $e = json_decode(trim($line), true);
    if (is_array($e) && isset($e['address'])) { $entries[] = $e; }
}
$total = count($entries);

if ($action === 'status') {
    flock($fh, LOCK_UN); fclose($fh);
    echo json_encode(['ok' => true, 'faucet' => $faucet, 'country' => $country,
                      'granted' => min($total, CAP_PER_COUNTRY), 'cap' => CAP_PER_COUNTRY,
                      'waitlist' => max(0, $total - CAP_PER_COUNTRY)]);
    exit;
}

// ---- claim: dedupe per address across ALL countries of this faucet -------
foreach (glob($dir . '/*.jsonl') as $file) {
    foreach (file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $e = json_decode($line, true);
        if (is_array($e) && isset($e['address']) && hash_equals($e['address'], $address)) {
            flock($fh, LOCK_UN); fclose($fh);
            $pos = isset($e['position']) ? (int)$e['position'] : 0;
            echo json_encode(['ok' => true, 'status' => $pos <= CAP_PER_COUNTRY ? 'granted' : 'waitlist',
                              'position' => $pos, 'cap' => CAP_PER_COUNTRY, 'note' => 'already registered']);
            exit;
        }
    }
}

// ---- rate limit: salted-hashed IP, max claims per day, never stored raw --
$salt_file = $DATA . '/.salt';
if (!is_file($salt_file)) { file_put_contents($salt_file, bin2hex(random_bytes(16))); }
$ip_key = hash('sha256', file_get_contents($salt_file) . '|' . ($_SERVER['REMOTE_ADDR'] ?? ''));
$rl_dir = $DATA . '/.rl';
if (!is_dir($rl_dir)) { mkdir($rl_dir, 0770, true); }
$rl_file = $rl_dir . '/' . substr($ip_key, 0, 32);
$stamps = is_file($rl_file) ? array_filter(array_map('intval', file($rl_file, FILE_IGNORE_NEW_LINES))) : array();
$stamps = array_values(array_filter($stamps, function ($t) { return $t > time() - 86400; }));
if (count($stamps) >= MAX_CLAIMS_PER_IP_DAY) { flock($fh, LOCK_UN); fclose($fh); fail(429, 'rate limit: try again tomorrow'); }
$stamps[] = time();
file_put_contents($rl_file, implode("\n", $stamps) . "\n");

// ---- append the reservation ---------------------------------------------
$position = $total + 1;                       // 1-based; ≤150 granted, >150 waitlist
$entry = array('address' => $address, 'country' => $country, 'position' => $position, 'ts' => time());
fseek($fh, 0, SEEK_END);
fwrite($fh, json_encode($entry) . "\n");
fflush($fh);
flock($fh, LOCK_UN);
fclose($fh);

$granted = $position <= CAP_PER_COUNTRY;
echo json_encode(['ok' => true, 'status' => $granted ? 'granted' : 'waitlist',
                  'position' => $granted ? $position : $position - CAP_PER_COUNTRY,
                  'cap' => CAP_PER_COUNTRY]);
