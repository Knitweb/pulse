"""A tiny, dependency-free, deterministic statevector simulator.

Just enough to *execute* the built-in circuit library so a quantum-circuit
proof-of-useful-work job can produce reproducible measurement counts. It is
deliberately minimal (pure Python, no numpy) and deterministic: the same QASM +
seed + shots always yields byte-identical integer counts, which is what the PoUW
verifier re-checks.

Supported gates: h x y z s t sdg tdg, rx ry rz, cx cz swap, ccx cswap, cp/cu1.
Unknown gate lines are ignored deterministically (a seam, not a full compiler),
so execution never crashes on an exotic instruction — verification only needs
reproducibility, not physical completeness.
"""

from __future__ import annotations

import cmath
import math
import random
import re

__all__ = ["simulate_counts", "MAX_QUBITS"]

MAX_QUBITS = 16  # 2^16 amplitudes; guards against accidental blow-ups


# --------------------------------------------------------------------------- #
# QASM parsing
# --------------------------------------------------------------------------- #
_ANGLE = {"pi": math.pi}


def _angle(expr: str) -> float:
    """Evaluate a simple QASM angle expression like 'pi/2', '-pi/4', '0.5'."""
    e = expr.strip().replace("pi", str(math.pi))
    # only digits, operators, dot, spaces, parens — safe to eval numerically
    if not re.fullmatch(r"[-+*/(). 0-9eE]*", e):
        return 0.0
    try:
        return float(eval(e, {"__builtins__": {}}, {}))  # noqa: S307 - sanitised above
    except Exception:
        return 0.0


def _qubits(qasm: str) -> int:
    n = 0
    for line in qasm.splitlines():
        m = re.match(r"\s*qreg\s+\w+\[(\d+)\]", line)
        if m:
            n += int(m.group(1))
    return n or 1


def _idxs(operand: str) -> list[int]:
    return [int(i) for i in re.findall(r"\[(\d+)\]", operand)]


# --------------------------------------------------------------------------- #
# Gate application on a flat statevector
# --------------------------------------------------------------------------- #
def _apply_1q(state: list[complex], n: int, q: int, m: tuple[complex, complex, complex, complex]) -> None:
    a, b, c, d = m
    step = 1 << q
    for base in range(0, 1 << n, step << 1):
        for off in range(step):
            i0 = base + off
            i1 = i0 + step
            x0, x1 = state[i0], state[i1]
            state[i0] = a * x0 + b * x1
            state[i1] = c * x0 + d * x1


def _apply_cx(state: list[complex], n: int, ctrl: int, tgt: int) -> None:
    for i in range(1 << n):
        if (i >> ctrl) & 1 and not (i >> tgt) & 1:
            j = i | (1 << tgt)
            state[i], state[j] = state[j], state[i]


def _apply_cz(state: list[complex], n: int, a: int, b: int) -> None:
    for i in range(1 << n):
        if (i >> a) & 1 and (i >> b) & 1:
            state[i] = -state[i]


def _apply_cphase(state: list[complex], n: int, a: int, b: int, theta: float) -> None:
    ph = cmath.exp(1j * theta)
    for i in range(1 << n):
        if (i >> a) & 1 and (i >> b) & 1:
            state[i] *= ph


def _apply_swap(state: list[complex], n: int, a: int, b: int) -> None:
    for i in range(1 << n):
        bit_a, bit_b = (i >> a) & 1, (i >> b) & 1
        if bit_a != bit_b:
            j = i ^ (1 << a) ^ (1 << b)
            if i < j:
                state[i], state[j] = state[j], state[i]


def _apply_ccx(state: list[complex], n: int, c1: int, c2: int, tgt: int) -> None:
    for i in range(1 << n):
        if (i >> c1) & 1 and (i >> c2) & 1 and not (i >> tgt) & 1:
            j = i | (1 << tgt)
            state[i], state[j] = state[j], state[i]


_INV_SQRT2 = 1.0 / math.sqrt(2.0)
_SINGLE = {
    "h": (_INV_SQRT2, _INV_SQRT2, _INV_SQRT2, -_INV_SQRT2),
    "x": (0, 1, 1, 0),
    "y": (0, -1j, 1j, 0),
    "z": (1, 0, 0, -1),
    "s": (1, 0, 0, 1j),
    "sdg": (1, 0, 0, -1j),
    "t": (1, 0, 0, cmath.exp(1j * math.pi / 4)),
    "tdg": (1, 0, 0, cmath.exp(-1j * math.pi / 4)),
}


def _rot(name: str, theta: float) -> tuple[complex, complex, complex, complex]:
    c, s = math.cos(theta / 2), math.sin(theta / 2)
    if name == "rx":
        return (c, -1j * s, -1j * s, c)
    if name == "ry":
        return (c, -s, s, c)
    # rz
    return (cmath.exp(-1j * theta / 2), 0, 0, cmath.exp(1j * theta / 2))


# --------------------------------------------------------------------------- #
# Public: simulate a circuit to a measurement histogram
# --------------------------------------------------------------------------- #
def simulate_counts(qasm: str, shots: int, seed: int) -> dict[str, int]:
    """Run *qasm* for *shots* shots seeded by *seed*; return a counts histogram.

    Bitstrings are big-endian over qubit index (q[0] is the leftmost bit), so the
    format matches the built-in library's convention. Deterministic: identical
    (qasm, shots, seed) always yields identical counts.
    """
    n = _qubits(qasm)
    if n > MAX_QUBITS:
        raise ValueError(f"circuit has {n} qubits; simulator caps at {MAX_QUBITS}")
    if shots <= 0:
        raise ValueError("shots must be positive")

    state = [0j] * (1 << n)
    state[0] = 1 + 0j

    for raw in qasm.splitlines():
        line = raw.strip().rstrip(";")
        if not line or line.startswith(("//", "OPENQASM", "include", "qreg", "creg", "measure", "barrier", "if")):
            continue
        m = re.match(r"([a-z]+)(\(([^)]*)\))?\s+(.*)", line)
        if not m:
            continue
        gate, _, arg, operands = m.groups()
        idx = _idxs(operands)
        if gate in _SINGLE and idx:
            _apply_1q(state, n, idx[0], _SINGLE[gate])
        elif gate in ("rx", "ry", "rz") and idx:
            _apply_1q(state, n, idx[0], _rot(gate, _angle(arg or "0")))
        elif gate in ("cx", "cnot") and len(idx) >= 2:
            _apply_cx(state, n, idx[0], idx[1])
        elif gate == "cz" and len(idx) >= 2:
            _apply_cz(state, n, idx[0], idx[1])
        elif gate in ("cp", "cu1", "cphase") and len(idx) >= 2:
            _apply_cphase(state, n, idx[0], idx[1], _angle(arg or "0"))
        elif gate == "swap" and len(idx) >= 2:
            _apply_swap(state, n, idx[0], idx[1])
        elif gate in ("ccx", "toffoli") and len(idx) >= 3:
            _apply_ccx(state, n, idx[0], idx[1], idx[2])
        elif gate in ("cswap", "fredkin") and len(idx) >= 3:
            # controlled swap: swap idx[1],idx[2] where idx[0]=1
            for i in range(1 << n):
                if (i >> idx[0]) & 1:
                    ba, bb = (i >> idx[1]) & 1, (i >> idx[2]) & 1
                    if ba and not bb:
                        j = i ^ (1 << idx[1]) ^ (1 << idx[2])
                        state[i], state[j] = state[j], state[i]
        # unknown gate → ignored deterministically

    # Probability distribution over basis states.
    probs = [abs(a) ** 2 for a in state]
    total = sum(probs) or 1.0
    # Deterministic cumulative sampling with a seeded Mersenne-Twister PRNG.
    rng = random.Random(seed)
    cum = []
    running = 0.0
    for p in probs:
        running += p / total
        cum.append(running)
    counts: dict[str, int] = {}
    for _ in range(shots):
        r = rng.random()
        # linear scan is fine for the small state sizes used here
        k = 0
        while k < len(cum) - 1 and r > cum[k]:
            k += 1
        bits = format(k, f"0{n}b")            # little-endian index -> string
        key = bits[::-1]                       # q[0] as leftmost bit (big-endian label)
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))
