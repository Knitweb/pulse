<?php
/* Per-host relay configuration. Only identity and federation live here;
 * operational limits have safe defaults in _lib.php and can be overridden
 * by define()-ing them in this file before _lib.php loads. */
define('RELAY_HOST_ID', '5mart.ml');
define('RELAY_PEER_STATUS', 'https://knitweb.art/api/relay/status.php'); // reachable once the domain is verified
