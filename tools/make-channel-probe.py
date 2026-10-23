#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate a quiet stereo channel-identification WAV; never plays audio or applies EQ."""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import sys
import wave


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('output', type=Path)
    args = ap.parse_args()
    if args.output.exists() or args.output.with_suffix('.json').exists():
        ap.error('output or metadata already exists')
    rate = 48000
    amplitude = 32767 * 10 ** (-36 / 20)
    samples = array.array('h')
    timeline = []
    frame = 0
    # 1 s silence, 0.5 s L, 1 s silence, 0.5 s R, 1 s silence.
    for label, duration, channel in [('silence', 1, None), ('left', .5, 0),
            ('silence', 1, None), ('right', .5, 1), ('silence', 1, None)]:
        count = int(duration * rate)
        timeline.append(dict(label=label, start_frame=frame, frames=count))
        for i in range(count):
            fade = min(1, i / (rate * .02), (count - 1 - i) / (rate * .02))
            value = round(amplitude * fade * math.sin(2 * math.pi * 750 * i / rate))
            samples.extend((value if channel == 0 else 0, value if channel == 1 else 0))
        frame += count
    peak = max(abs(x) for x in samples)
    if sys.byteorder != 'little':
        samples.byteswap()
    with wave.open(str(args.output), 'wb') as w:
        w.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
        w.writeframes(samples.tobytes())
    metadata = dict(rate=rate, channels=2, frames=frame, peak_dbfs=-36,
                    sample_peak=peak, frequency_hz=750, timeline=timeline,
                    sha256=hashlib.sha256(args.output.read_bytes()).hexdigest(),
                    instructions='Manual playback only at low device volume. PCM level is not acoustic SPL. '
                    'Record physical top/bottom separately for each orientation and Dolby state. '
                    'Do not infer gain correction from this channel test.')
    args.output.with_suffix('.json').write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    main()
