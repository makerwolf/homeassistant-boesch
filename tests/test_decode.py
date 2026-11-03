"""Dekodierung der 16-Bit-Register und Blockbildung (ohne Home Assistant)."""

from __future__ import annotations

import pytest

from custom_components.boesch.const import MAX_BLOCK_GAP, MAX_BLOCK_SIZE
from custom_components.boesch.coordinator import _build_blocks, _decode
from custom_components.boesch.registers import REGISTERS, DeviceKey, Reg


def _reg(address: int = 0, **kwargs) -> Reg:
    return Reg(key=f"k{address}", name="n", device=DeviceKey.WANDA, address=address, **kwargs)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (352, 35.2),     # Vorlauf 35,2 °C
        (0xFFCE, -5.0),  # -50 Zehntel im Zweierkomplement
        (0x8000, -3276.8),
        (0, 0.0),
    ],
)
def test_int16_scale(raw: int, expected: float) -> None:
    """Kernbefund: int16 + Faktor 0,1, nicht float32."""
    assert _decode(_reg(data_type="int16", scale=0.1, precision=1), raw) == expected


def test_uint16_stays_positive() -> None:
    """uint16 (z. B. Laufzeiten) darf über 0x8000 nicht negativ werden."""
    assert _decode(_reg(data_type="uint16", scale=0.1, precision=1), 0xFFFF) == 6553.5


def test_scale_one_returns_int() -> None:
    value = _decode(_reg(), 4)
    assert value == 4
    assert isinstance(value, int)


def test_clamping() -> None:
    """min/max kappen, sie filtern nicht."""
    reg = _reg(scale=0.1, precision=1, min_value=0.0, max_value=100.0)
    assert _decode(reg, 0xFFFF) == 0.0      # -0,1 -> 0
    assert _decode(reg, 2000) == 100.0      # 200,0 -> 100


def test_raw_zero_is_valid() -> None:
    """Rohwert 0 ist ein gültiger Zustand (z. B. Status Heizkreis = Aus)."""
    assert _decode(_reg(), 0) == 0


def test_blocks_contiguous() -> None:
    regs = [_reg(a) for a in (100, 101, 102, 103)]
    assert _build_blocks(regs) == [(100, 4)]


def test_blocks_small_gap_read_along() -> None:
    regs = [_reg(100), _reg(100 + MAX_BLOCK_GAP)]
    assert _build_blocks(regs) == [(100, MAX_BLOCK_GAP + 1)]


def test_blocks_large_gap_split() -> None:
    regs = [_reg(100), _reg(100 + MAX_BLOCK_GAP + 1)]
    assert _build_blocks(regs) == [(100, 1), (100 + MAX_BLOCK_GAP + 1, 1)]


def test_blocks_unsorted_input() -> None:
    regs = [_reg(5), _reg(1), _reg(3)]
    assert _build_blocks(regs) == [(1, 5)]


def test_blocks_respect_max_size() -> None:
    regs = [_reg(a) for a in range(MAX_BLOCK_SIZE + 10)]
    blocks = _build_blocks(regs)
    assert all(count <= MAX_BLOCK_SIZE for _, count in blocks)
    covered = [a for start, count in blocks for a in range(start, start + count)]
    assert covered == list(range(MAX_BLOCK_SIZE + 10))


def test_blocks_empty() -> None:
    assert _build_blocks([]) == []


def test_register_model_consistent() -> None:
    """Eindeutige Keys und Adressen je Gerät, nur 16-Bit-Datentypen."""
    keys = [r.key for r in REGISTERS]
    assert len(keys) == len(set(keys))
    # Ausnahme: Hydrobox 301 ist in der Bösch-Doku mehrfach vergeben (CLAUDE.md).
    addresses = [(r.device, r.address) for r in REGISTERS if r.address != 301]
    assert len(addresses) == len(set(addresses))
    for reg in REGISTERS:
        assert reg.data_type in ("int16", "uint16"), reg.key
