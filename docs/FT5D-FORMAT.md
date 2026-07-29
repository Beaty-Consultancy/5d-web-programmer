# Yaesu FT-5D `MEMORY.dat` format

Documentation of the SD-card memory-channel file
(`FT5D_MEMORY-CH/MEMORY.dat`) written by the Yaesu FT-5DE / FT-5DR. Verified
byte-for-byte against the radio's own files. This describes an interoperable file
format for interoperability purposes; it contains no vendor software.

The file is **44,160 bytes** (`0xAC80`). All multi-byte integers noted below are
big-endian. Frequencies are stored as 3-byte packed BCD of `round(MHz × 1000)`
(i.e. integer kHz): `145.6000 MHz → 145600 → 14 56 00`.

## File regions

| Offset | Size | Contents |
|--------|------|----------|
| `0x0000` | 4,800 | Scan-bank membership — 24 banks × 100 slots × 2 bytes |
| `0x12C0` | 900 | Channel directory — 1 byte per channel |
| `0x1800` | 900 × 32 | Memory channel records |
| `0x8880` | — | Skip-memory channel records |
| `0x9500` | 100 × 32 | PMS (Programmable Memory Scan) edge records |
| `0xAB19` | 3 | Checksum |

> These offsets are a constant `−5440` bytes from the addresses used inside the
> radio's full image, if you are cross-referencing a full backup.

## Channel directory (`0x12C0`, 1 byte/channel)

| Bit(s) | Meaning |
|--------|---------|
| 0 | Channel present / in use |
| 1 | (in-use flag, complementary) |
| 2–3 | Scan setting: `0` normal, `1` skip, `2` PMS-only |
| 6 | Radio-receive frequency flag |
| 7 | Band-B receive flag |

A record at `0x1800 + (n × 32)` is only valid when directory byte `n` has bit 0 set.

## Channel record (32 bytes)

Offsets are relative to the start of each record.

| Byte | Bits | Field |
|------|------|-------|
| 0 | 0–3 | Band/mag type (derived from frequency) |
| 0 | 4 | Clock shift |
| 0 | 5 | Half-deviation (narrow FM) |
| 1 | 0–3 | Step index (see table) |
| 1 | 4–5 | Shift direction: `0` simplex, `1` −, `2` +, `3` explicit TX |
| 1 | 6–7 | Analog modulation: `0` FM, `1` AM, `2` WFM |
| 2–4 | | RX frequency (3-byte BCD kHz) |
| 5 | 0–3 | Squelch type (see table) |
| 5 | 4–5 | Digital/analog: `0` analog, `1` AMS, `2` DN, `3` VW |
| 5 | 6–7 | TX power: `0` L1 (0.3 W), `1` L2 (1 W), `2` L3 (2.5 W), `3` High (5 W) |
| 6–7 | | Name width flags |
| 8–23 | | Name / alpha tag (16 bytes, ASCII, `0xFF`-padded) |
| 24–26 | | Shift amount (BCD kHz) for shift dir 1/2, or explicit TX frequency for shift dir 3 |
| 27 | | CTCSS tone index (see table) |
| 28 | | DCS code index (see table) |
| 29 | 0–4 | PR tone |
| 29 | 5–7 | DCS polarity |
| 30 | 0–3 | S-meter squelch |
| 30 | 4–5 | Vibrator |
| 30 | 6 | VW flag (set when digital = VW) |
| 30 | 7 | AMS flag (set when digital = AMS) |
| 31 | 0–2 | Bell |
| 31 | 3 | Auto-mode (AMS) |
| 31 | 4 | Auto-step |
| 31 | 5 | Attenuator |
| 31 | 7 | Radio receive |

For a repeater, TX = RX ∓ (shift amount) for shift dir 1/2, or the explicit TX
frequency for shift dir 3. `TONE` squelch transmits the CTCSS tone to open a
repeater; `TSQL` also mutes your receiver until it hears the tone back.

## Value tables

**CTCSS tones (index → Hz)** — 50 entries: 67.0, 69.3, 71.9, 74.4, 77.0, 79.7,
82.5, 85.4, 88.5, 91.5, 94.8, 97.4, 100.0, 103.5, 107.2, 110.9, 114.8, 118.8,
123.0, 127.3, 131.8, 136.5, 141.3, 146.2, 151.4, 156.7, 159.8, 162.2, 165.5,
167.9, 171.3, 173.8, 177.3, 179.9, 183.5, 186.2, 189.9, 192.8, 196.6, 199.5,
203.5, 206.5, 210.7, 218.1, 225.7, 229.1, 233.6, 241.8, 250.3, 254.1.

**Step (index → kHz)** — 0:5.0, 1:6.25, 2:8.33, 3:10.0, 4:12.5, 5:15.0, 6:20.0,
7:25.0, 8:50.0, 9:100.0, 10:9.0.

**Squelch type (index)** — 0:OFF, 1:TONE, 2:TONE-SQL, 3:DCS, 4:REV-TONE, 6:PR,
7:PAGER, 9:D-CD, 10:TONE-DCS, 11:D-CD-TONE.

**DCS codes (index → code)** — 104 standard DCS codes in ascending order, starting
023, 025, 026, 031, 032, 036, 043 … 743, 754. See the full array in
[`../engine/ft5d_codeplug.py`](../engine/ft5d_codeplug.py).

## Scan-bank membership (`0x0000`)

24 banks, each 100 × 2-byte slots. Each entry is `(memory_type << 11) | index`;
`memory_type = 0` is normal memory and `index` is the 0-based channel number.
Empty slots are `0xFFFF`. A channel may appear in multiple banks. Bank *names* are
**not** stored here (they live in the radio's full backup), so tools operating only
on `MEMORY.dat` see banks as numbers 1–24.

## PMS scan edges (`0x9500`)

Programmable Memory Scan edges use the **same 32-byte record format** as channels,
in LO/HI pairs bounding a scan range. Set them to Analog or AMS so the radio stops
on FM signals within the range.

## Checksum (`0xAB19`)

3 bytes, big-endian, equal to `sum(file[0 : 0xAB19]) & 0xFFFFFF`. Recompute and
write these three bytes after any edit or the radio will reject the file.

## `BACKUP.dat` — the full clone

The SD "Backup" function writes a second file, `FT5D/BACKUP/BACKUP.dat`
(**130,496 bytes**, `0x1FDC0`), which is a full image of the radio. Restoring it
replaces the whole configuration, so preserve every byte you don't intend to change.

`MEMORY.dat` is a window of this image offset by `−5440`, so the memory-channel
regions above appear here at their native addresses (add 5440): bank membership at
`0x1540`, directory at `0x2800`, channels at `0x2D40`, skip at `0x9DC0`, PMS at
`0xAA40`. The record and value-table formats are identical.

Additional regions (byte offsets are direct in this file):

| Offset | Contents |
|--------|----------|
| `0x0440` (1088) | Set-mode (radio menu) — mostly one byte per setting; bank-link bitfield at `+252` (3 bytes) |
| `0x0940` (2368) | DTMF autodial — 10 memories × 16 digit bytes |
| `0x0EF4` (3828) | Bank names — 24 × 18-byte slots (u16 width BE + 16-byte name) |
| `0xBEC0` (48832) | APRS config — callsign `+2` (6 B) + SSID `+8`, beacon flag `+11` bit6, interval `+28`, digipath `+325`, SmartBeaconing `+300` |

**Character encodings.** Channel/bank names and APRS text are ASCII (`0x20–0x7E`),
`0xFF`-padded. APRS/GM callsigns use ASCII restricted to `A–Z 0–9 - /`. DTMF uses a
compact index table: `0–9`→0–9, `A–D`→10–13, `*`→14, `#`→15, `-`→16, empty `0xFF`.

**Checksum.** Different from `MEMORY.dat`: a **4-byte big-endian** value at offset
`130492` (`0x1FDBC`) equal to `sum(file[0 : 130492])` (the whole file except its last
four bytes). Recompute after any edit.
