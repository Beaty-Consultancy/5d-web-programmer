#!/usr/bin/env python3
"""Runnable example for the FT-5D codeplug engine.

Builds a few channel records and (optionally) a full MEMORY.dat. `record()` is
fully self-contained; `build()` needs a radio-exported MEMORY.dat as a structural
template (it preserves the header/config regions and only rewrites the channel,
scan-bank and PMS areas). Export a template once from your radio:
    MENU -> SD CARD -> 2 MEMORY CH -> Write to SD
then copy <SD>/FT5D_MEMORY-CH/MEMORY.dat next to this script as template.dat.

Usage:
    python3 example.py            # print example records
    python3 example.py template.dat out.dat   # build a full codeplug
"""
import sys
from ft5d_codeplug import record, build

# A small, illustrative channel list. Each dict is passed straight to record().
CHANNELS = [
    dict(mhz=145.500, tag="2M CALL",  mode="AMS", step_khz=12.5),
    dict(mhz=145.600, tag="GB3AS",    mode="AMS", offset_mhz=-0.6,
         tone_hz=77.0, sql="TONE", step_khz=15.0),
    dict(mhz=433.325, tag="GB3CA",    mode="AMS", offset_mhz=+1.6,
         tone_hz=77.0, sql="TONE", step_khz=25.0),
    dict(mhz=433.075, tag="70CM CQ",  mode="AMS", step_khz=12.5),
    dict(mhz=123.600, tag="AIRBAND",  mode="AM",  step_khz=25.0),
]

# PMS scan-edge pairs (LO, HI, LO, HI, ...) and example scan banks.
PMS = [
    dict(mhz=145.000, tag="2M LOW",  mode="AMS", step_khz=12.5),
    dict(mhz=146.000, tag="2M HIGH", mode="AMS", step_khz=12.5),
]
BANKS = {1: [2, 3], 2: [1, 4]}   # bank 1 = repeaters, bank 2 = simplex


def main():
    print("Example 32-byte channel records (hex):\n")
    for ch in CHANNELS:
        print(f"  {ch['tag']:9s} {record(**ch).hex()}")

    if len(sys.argv) == 3:
        base = open(sys.argv[1], "rb").read()
        data = build(base, CHANNELS, pms=PMS, banks=BANKS)
        open(sys.argv[2], "wb").write(data)
        print(f"\nWrote {len(data)} bytes -> {sys.argv[2]}")
        print("Copy it to <SD>/FT5D_MEMORY-CH/MEMORY.dat and Read from SD on the radio.")
    else:
        print("\n(pass a template.dat and output path to build a full MEMORY.dat)")


if __name__ == "__main__":
    main()
