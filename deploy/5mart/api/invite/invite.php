<?php
/**
 * invite.php — invite links with a visible queue position (features doc #5).
 *
 * Built-in, measurable word of mouth, same zero-PII discipline as the faucet
 * next door: the only things stored are public pls1 addresses, a derived code,
 * and integer counters — no names, no emails, no raw IPs (rate limiting uses a
 * salted hash, never written in clear).
 *
 *   POST api/invite/create  { "address": "pls1…" }
 *       -> { "ok": true, "code": "kw-XXXXXXXX", "recruits": <int> }
 *          (deterministic per address — calling twice returns the same code)
 *   POST api/invite/redeem  { "code": "kw-…", "address": "pls1…" }
 *       -> { "ok": true, "inviter_recruits": <int>, "your_position": <int> }
 *          (idempotent per (code,address); an address cannot redeem its own code)
 *   GET  api/invite/status?code=kw-…
 *       -> { "ok": true, "recruits": <int> }
 *   GET  api/invite/health  -> { "ok": true, "service": "knitweb-invite", ... }
 *
 * The code is derived (salted sha256 of the address) so it is stable and
 * unguessable-from-nothing, yet reproducible for its owner. Redemptions are a
 * per-code append-only JSONL ledger; recruits = distinct redeemer addresses.
 * Dependency-free PHP, TransIP-friendly, same conventions as faucet.php / #337.
 */

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');
header('Cache-Control: no-store');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') { http_response_code(204); exit; }

const MAX_REDEEM_PER_IP_DAY = 20;
$DATA = __DIR__ . '/_state';

function fail($code, $msg) { http_response_code($code); echo json_encode(['ok' => false, 'error' => $msg]); exit; }
function valid_addr($a) { return is_string($a) && preg_match('/^pls1[a-z2-7]{20,64}$/', $a); }
function valid_code($c) { return is_string($c) && preg_match('/^kw-[a-f0-9]{8}$/', $c); }

$action = isset($_GET['action']) ? $_GET['action'] : '';
if ($action === '') {
    $tail = basename((string)parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH));
    if (in_array($tail, array('create', 'redeem', 'status', 'health'), true)) { $action = $tail; }
}

if ($action === 'health') {
    echo json_encode(['ok' => true, 'service' => 'knitweb-invite', 'time' => time()]);
    exit;
}

if (!is_dir($DATA) && !mkdir($DATA, 0770, true) && !is_dir($DATA)) { fail(500, 'storage unavailable'); }

// Salt: shared with nobody, used only to derive codes + hash IPs. Never exposed.
$salt_file = $DATA . '/.salt';
if (!is_file($salt_file)) { file_put_contents($salt_file, bin2hex(random_bytes(16))); }
$salt = file_get_contents($salt_file);

function code_for($salt, $address) { return 'kw-' . substr(hash('sha256', $salt . '|invite|' . $address), 0, 8); }
function ledger_path($DATA, $code) { return $DATA . '/' . $code . '.jsonl'; }
function count_recruits($path) {
    if (!is_file($path)) { return 0; }
    $seen = array();
    foreach (file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        $e = json_decode($line, true);
        if (is_array($e) && isset($e['address'])) { $seen[$e['address']] = true; }
    }
    return count($seen);
}

/* ---- create: deterministic code for an address -------------------------- */
if ($action === 'create') {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') { fail(405, 'POST only'); }
    $body = json_decode((string)file_get_contents('php://input'), true);
    if (!is_array($body) || !valid_addr($body['address'] ?? null)) { fail(400, 'address must be a pls1 base32 address'); }
    $code = code_for($salt, $body['address']);
    // Record ownership once so status/redeem can exist without the owner online.
    $owner_file = $DATA . '/' . $code . '.owner';
    if (!is_file($owner_file)) { file_put_contents($owner_file, $body['address']); }
    echo json_encode(['ok' => true, 'code' => $code, 'recruits' => count_recruits(ledger_path($DATA, $code))]);
    exit;
}

/* ---- status: how many joined through this code -------------------------- */
if ($action === 'status') {
    $code = isset($_GET['code']) ? trim((string)$_GET['code']) : '';
    if (!valid_code($code)) { fail(400, 'bad code'); }
    echo json_encode(['ok' => true, 'code' => $code, 'recruits' => count_recruits(ledger_path($DATA, $code))]);
    exit;
}

/* ---- redeem: register that an address joined through a code ------------- */
if ($action !== 'redeem') { fail(404, 'unknown action'); }
if ($_SERVER['REQUEST_METHOD'] !== 'POST') { fail(405, 'POST only'); }
$body = json_decode((string)file_get_contents('php://input'), true);
if (!is_array($body)) { fail(400, 'invalid JSON'); }
$code = isset($body['code']) ? trim((string)$body['code']) : '';
$address = $body['address'] ?? null;
if (!valid_code($code)) { fail(400, 'bad code'); }
if (!valid_addr($address)) { fail(400, 'address must be a pls1 base32 address'); }

$owner_file = $DATA . '/' . $code . '.owner';
if (is_file($owner_file) && hash_equals(trim(file_get_contents($owner_file)), $address)) {
    fail(400, 'cannot redeem your own invite');
}

// Rate limit: salted-hashed IP, never stored raw.
$ip_key = hash('sha256', $salt . '|ip|' . ($_SERVER['REMOTE_ADDR'] ?? ''));
$rl_dir = $DATA . '/.rl';
if (!is_dir($rl_dir)) { mkdir($rl_dir, 0770, true); }
$rl = fopen($rl_dir . '/' . substr($ip_key, 0, 32), 'c+');
if ($rl === false || !flock($rl, LOCK_EX)) { if ($rl) { fclose($rl); } fail(503, 'busy, retry'); }
$stamps = array();
while (($line = fgets($rl)) !== false) { $t = (int)trim($line); if ($t > time() - 86400) { $stamps[] = $t; } }
if (count($stamps) >= MAX_REDEEM_PER_IP_DAY) { flock($rl, LOCK_UN); fclose($rl); fail(429, 'rate limit: try again tomorrow'); }

$ledger = ledger_path($DATA, $code);
$fh = fopen($ledger, 'c+');
if ($fh === false || !flock($fh, LOCK_EX)) { if ($fh) { fclose($fh); } flock($rl, LOCK_UN); fclose($rl); fail(503, 'busy, retry'); }

$addresses = array(); $position = 0;
rewind($fh);
while (($line = fgets($fh)) !== false) {
    $e = json_decode(trim($line), true);
    if (is_array($e) && isset($e['address'])) { $addresses[$e['address']] = ($e['position'] ?? 0); }
}
if (isset($addresses[$address])) {
    // Idempotent: already redeemed — do not double-count or spend a rate slot.
    flock($fh, LOCK_UN); fclose($fh); flock($rl, LOCK_UN); fclose($rl);
    echo json_encode(['ok' => true, 'inviter_recruits' => count($addresses),
                      'your_position' => (int)$addresses[$address], 'note' => 'already redeemed']);
    exit;
}
$position = count($addresses) + 1;
fseek($fh, 0, SEEK_END);
fwrite($fh, json_encode(array('address' => $address, 'position' => $position, 'ts' => time())) . "\n");
fflush($fh); flock($fh, LOCK_UN); fclose($fh);

$stamps[] = time();
rewind($rl); ftruncate($rl, 0); fwrite($rl, implode("\n", $stamps) . "\n");
fflush($rl); flock($rl, LOCK_UN); fclose($rl);

echo json_encode(['ok' => true, 'inviter_recruits' => $position, 'your_position' => $position]);
