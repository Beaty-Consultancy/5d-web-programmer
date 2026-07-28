"""FT-5DE codeplug engine — encodes a radio-valid SD MEMORY.dat.

Derived byte-for-byte from Yaesu ADMS-14's decompiled `Memory.Encode()` and
validated against radio-authored records (GB3CA ch44, airband AM). Supersedes
the earlier hand-reverse-engineered version, which mis-placed the shift bits
(byte1 bit1 instead of bits4-5) and wrote every repeater as simplex.

MEMORY.dat is a window of the radio image at ADMS offset 5440, so
SD_offset = ADMS_addr - 5440:
  0x0000  scan-bank membership  (24 banks x 100 slots x 2 bytes)
  0x12c0  channel directory     (1 byte/chan: bit0 present, bits2-3 skip)
  0x1800  memory channels        (900 x 32-byte records)
  0x8880  skip-memory channels
  0x9500  PMS scan-edge pairs    (same 32-byte record format)
  0xab19  checksum               (big-endian sum(file[:0xab19]))

32-byte record layout (offset within record):
  0  bits0-3 MagType | bit4 ClockShift | bit5 HalfDev(narrow)
  1  bits0-3 Step | bits4-5 ShiftDir(0=simplex 1=- 2=+ 3=explicitTX) | bits6-7 Mode(0FM 1AM 2WFM)
  2-4  RxFrq BCD (freq*1000 kHz)          | 6-7 name-width | 8-23 name (16B, 0xff)
  5  bits0-3 SqlType | bits4-5 DigAnalog(0analog 1AMS 2DN 3VW) | bits6-7 TxPower
  24-26 ShiftFrq BCD (amount) or TxFrq (ShiftDir==3)
  27 ToneIdx | 28 DcsIdx | 29 bits0-4 PrTone + bits5-7 DcsDim
  30 bits0-3 Smeter | bits4-5 Vibrator | bit6 VW-flag | bit7 digital-capable
  31 0x18 = AutoMode + AutoStep (radio default)
"""
from __future__ import annotations

BANK0 = 0x0000
DIR0 = 0x12c0
REC0 = 0x1800
PMS0 = 0x9500
CKSUM_OFF = 0xab19
RECLEN = 32
NUM_BANKS = 24
BANK_SLOTS = 100          # channels per bank
NCHAN = 900               # normal memory channels

TONES = [67.0,69.3,71.9,74.4,77.0,79.7,82.5,85.4,88.5,91.5,94.8,97.4,100.0,103.5,
         107.2,110.9,114.8,118.8,123.0,127.3,131.8,136.5,141.3,146.2,151.4,156.7,
         159.8,162.2,165.5,167.9,171.3,173.8,177.3,179.9,183.5,186.2,189.9,192.8,
         196.6,199.5,203.5,206.5,210.7,218.1,225.7,229.1,233.6,241.8,250.3,254.1]
TONE_PARK = 12            # radio stores 100.0 (index 12) when CTCSS unused

DCS_CODES = ["023","025","026","031","032","036","043","047","051","053","054",
    "065","071","072","073","074","114","115","116","122","125","131","132","134",
    "143","145","152","155","156","162","165","172","174","205","212","223","225",
    "226","243","244","245","246","251","252","255","261","263","265","266","271",
    "274","306","311","315","325","331","332","343","346","351","356","364","365",
    "371","411","412","413","423","431","432","445","446","452","454","455","462",
    "464","465","466","503","506","516","523","526","532","546","565","606","612",
    "624","627","631","632","654","662","664","703","712","723","731","732","734",
    "743","754"]

# byte1 low-nibble step index -> kHz (full 11-entry ADMS tbl_Step)
STEP_KHZ = {5.0:0, 6.25:1, 8.33:2, 10.0:3, 12.5:4, 15.0:5, 20.0:6, 25.0:7,
            50.0:8, 100.0:9, 9.0:10}
SQL = {"OFF":0, "TONE":1, "TSQL":2, "DCS":3, "REVTONE":4, "PR":6, "PAGER":7,
       "DCD":9, "TONEDCS":10, "DCDTONE":11}
DIG = {"FM":0, "AM":0, "WFM":0, "AMS":1, "DN":2, "VW":3}   # DigAnalog (byte5 4-5)
MODE = {"FM":0, "AM":1, "WFM":2, "AMS":0, "DN":0, "VW":0}  # analog Mode (byte1 6-7)
POWER = {"L1":0, "L2":1, "L3":2, "HIGH":3}
DCS_DIM = {"RXN_TXN":0, "RXI_TXN":1, "RXB_TXN":2, "RXN_TXI":3, "RXI_TXI":4, "RXB_TXI":5}


def _magtype(mhz: float) -> int:
    if mhz < 2: return 4
    if 108 <= mhz < 137: return 1
    if 137 <= mhz < 300: return 2
    if mhz >= 300: return 3
    return 7


def _bcd(mhz: float) -> bytes:
    s = f"{int(round(mhz * 1000)):06d}"
    return bytes((int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)))


def tone_index(hz: float | None) -> int:
    if hz is None: return TONE_PARK
    return TONES.index(min(TONES, key=lambda t: abs(t - hz)))


def dcs_index(code) -> int:
    s = f"{int(code):03d}"
    if s not in DCS_CODES:
        raise ValueError(f"invalid DCS code {code!r}")
    return DCS_CODES.index(s)


def record(mhz: float, tag: str, mode: str = "AMS", offset_mhz: float = 0.0,
           shiftdir: int | None = None, tone_hz: float | None = None,
           sql: str = "OFF", dcs_code=None, dcs_dim: str = "RXN_TXN",
           power: str = "HIGH", step_khz: float | None = None,
           narrow: bool = False) -> bytes:
    """Build one 32-byte channel/PMS record (matches ADMS Memory.Encode)."""
    if mode not in DIG:
        raise ValueError(f"unknown mode {mode!r}; use one of {sorted(DIG)}")
    if sql not in SQL:
        raise ValueError(f"unknown sql {sql!r}; use one of {sorted(SQL)}")
    if power not in POWER:
        raise ValueError(f"unknown power {power!r}; use one of {sorted(POWER)}")
    if step_khz is not None and step_khz not in STEP_KHZ:
        raise ValueError(f"unknown step_khz {step_khz}; use one of {sorted(STEP_KHZ)}")
    dig = DIG[mode]; amode = MODE[mode]
    r = bytearray(32)
    r[0] = _magtype(mhz) | (0x20 if narrow else 0)
    if shiftdir is None:
        shiftdir = 0 if abs(offset_mhz) < 1e-6 else (1 if offset_mhz < 0 else 2)
    step_idx = STEP_KHZ[step_khz] if step_khz is not None else 0
    r[1] = (step_idx & 0xF) | ((shiftdir & 3) << 4) | ((amode & 3) << 6)
    r[2:5] = _bcd(mhz)
    st = SQL[sql]
    if sql == "OFF":
        if dcs_code is not None: st = SQL["DCS"]
        elif tone_hz is not None: st = SQL["TONE"]
    r[5] = (st & 0xF) | ((dig & 3) << 4) | ((POWER[power] & 3) << 6)
    r[8:24] = tag.encode("ascii", "replace")[:16].ljust(16, b"\xff")
    if shiftdir == 3:
        r[24:27] = _bcd(mhz + offset_mhz)
    elif shiftdir in (1, 2):
        r[24:27] = _bcd(abs(offset_mhz))
    r[27] = tone_index(tone_hz)
    r[28] = dcs_index(dcs_code) if dcs_code is not None else 0
    r[29] = 0x0d | ((DCS_DIM.get(dcs_dim, 0) & 7) << 5)
    r[30] = (0x80 if dig == 1 else 0) | (0x40 if dig == 3 else 0)  # bit7=AMS, bit6=VW
    r[31] = 0x18
    assert len(r) == RECLEN
    return bytes(r)


def _dir_byte(skip: bool = False) -> int:
    return 0x03 | ((1 if skip else 0) << 2)          # present + optional skip


def _write_block(b: bytearray, base: int, channels: list[dict], clear: int):
    """Write records from `base`, updating the directory for the normal block."""
    for i in range(clear):
        o = base + i * RECLEN
        b[o:o + RECLEN] = b"\xff" * RECLEN
    for i, ch in enumerate(channels):
        o = base + i * RECLEN
        skip = ch.pop("skip", False)
        b[o:o + RECLEN] = record(**ch)
        if base == REC0:
            b[DIR0 + i] = _dir_byte(skip)


def set_banks(b: bytearray, banks: dict[int, list[int]]):
    """banks: {bank_number(1-24): [channel_number(1-based), ...]}.

    Membership is by reference, so a channel may sit in several banks.
    Entry = (memtype<<11)|index; memtype 0 = normal memory; 0xFFFF = empty.
    """
    for bank in range(NUM_BANKS):
        base = BANK0 + bank * BANK_SLOTS * 2
        b[base:base + BANK_SLOTS * 2] = b"\xff" * (BANK_SLOTS * 2)
    for bank_no, chans in banks.items():
        if not 1 <= bank_no <= NUM_BANKS:
            raise ValueError(f"bank number {bank_no} out of range 1..{NUM_BANKS}")
        base = BANK0 + (bank_no - 1) * BANK_SLOTS * 2
        for slot, ch_no in enumerate(chans[:BANK_SLOTS]):
            if not 1 <= ch_no <= NCHAN:
                raise ValueError(f"channel {ch_no} in bank {bank_no} out of range 1..{NCHAN}")
            val = (0 << 11) | ((ch_no - 1) & 0x7FF)      # normal memory
            b[base + slot * 2] = (val >> 8) & 0xFF
            b[base + slot * 2 + 1] = val & 0xFF


def build(base: bytes, channels: list[dict], pms: list[dict] | None = None,
          banks: dict[int, list[int]] | None = None,
          clear_slots: int = 200) -> bytes:
    """Assemble a MEMORY.dat: `channels` from slot 1, optional `pms` scan-edge
    pairs and `banks` membership. `base` is a radio-exported template."""
    b = bytearray(base)
    for i in range(clear_slots):
        b[DIR0 + i] = 0x00
    _write_block(b, REC0, [dict(c) for c in channels], clear_slots)
    if pms:
        _write_block(b, PMS0, [dict(c) for c in pms], 100)
    if banks:
        set_banks(b, banks)
    ck = sum(b[:CKSUM_OFF]) & 0xffffff
    b[CKSUM_OFF:CKSUM_OFF + 3] = ck.to_bytes(3, "big")
    return bytes(b)
