#!/usr/bin/env python3
"""Windows audio clock. winmm/MCI subprocess speaking the AudioClock.swift protocol:
stdin commands play/pause/seek <t>/volume <v>/quit, one JSON state line per frame on stdout.
MCI devices are bound to the thread that opened them, so every MCI call runs on that thread."""
from __future__ import annotations
import json, queue, sys, threading, time, traceback
from ctypes import windll, create_unicode_buffer
from pathlib import Path

mci_send = windll.winmm.mciSendStringW

def mci(command):
    out = create_unicode_buffer(256)
    code = mci_send(command, out, 256, 0)
    return code, out.value

def mci_error(code):
    buf = create_unicode_buffer(256)
    windll.winmm.mciGetErrorStringW(code, buf, 256)
    return buf.value or f'MCI error {code}'

def main():
    if hasattr(sys.stdout, 'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) < 2:
        print('Audio error: missing audio path', file=sys.stderr);return 1
    path = str(Path(sys.argv[1]).resolve())
    device = 'waveaudio' if path.lower().endswith('.wav') else 'mpegvideo'
    code, _ = mci(f'open "{path}" type {device} alias mv wait')
    if code:
        print(f'Audio error: {mci_error(code)}', file=sys.stderr);return 1
    mci('set mv time format milliseconds')
    _, length = mci('status mv length')
    try:duration = max(0., int(length or 0) / 1000.)
    except ValueError:duration = 0.
    if duration <= 0:
        mci('close mv wait')
        print(f'Audio error: cannot determine duration of {path}', file=sys.stderr);return 1
    commands = queue.Queue()

    def read_commands():
        # stdin reader only parses and enqueues; the device owner thread executes.
        try:
            for line in sys.stdin:
                fields = line.split()
                if fields:
                    commands.put(fields)
                    if fields[0] == 'quit':return
        except Exception:
            traceback.print_exc()
        finally:
            commands.put(None)

    threading.Thread(target=read_commands, daemon=True).start()

    def execute(fields):
        command, rest = fields[0], fields[1:]
        if command == 'play':mci('play mv')
        elif command == 'pause':mci('pause mv wait')
        elif command == 'seek' and rest:
            try:t = min(max(0., float(rest[0])), max(0., duration - .01))
            except ValueError:return
            mci(f'seek mv to {int(t*1000)} wait')
        elif command == 'volume' and rest:
            try:v = min(1., max(0., float(rest[0])))
            except ValueError:return
            mci(f'setaudio mv volume to {int(round(v*1000))}')

    mci('setaudio mv volume to 750')
    try:
        while True:
            stop = False
            while True:
                try:fields = commands.get_nowait()
                except queue.Empty:break
                if fields is None or fields[0] == 'quit':stop = True;break
                execute(fields)
            if stop:break
            code, mode = mci('status mv mode')
            if code:
                print(json.dumps({'error': mci_error(code)}), flush=True);continue
            _, position = mci('status mv position')
            try:seconds = max(0., int(position or 0) / 1000.)
            except ValueError:seconds = 0.
            print(json.dumps({'time': seconds, 'duration': duration, 'playing': mode == 'playing'}), flush=True)
            time.sleep(1 / 60)
    finally:
        mci('close mv wait')
    return 0

if __name__ == '__main__':
    sys.exit(main())
