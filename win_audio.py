"""Windows audio engine built on miniaudio.

Drop-in replacement for the macOS Swift ``audio-clock`` helper.  It exposes the
same surface the player expects:

    audio.state   -> dict {time, duration, playing}
    audio.error   -> str
    audio.command('play' | 'pause' | 'seek N' | 'volume N' | 'quit')
    audio.poll()  -> None while alive
    audio.close()
"""
from __future__ import annotations

import array
import threading
import time


class WinAudio:
    def __init__(self, path: str):
        self.error = ""
        self.last = time.monotonic()
        self._quit = False
        self._lock = threading.Lock()

        try:
            import miniaudio
        except ImportError as exc:
            raise RuntimeError(
                "缺少音频库 miniaudio，请先运行：python -m pip install miniaudio"
            ) from exc

        try:
            decoded = miniaudio.decode_file(
                path,
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=2,
                sample_rate=44100,
            )
        except Exception as exc:  # noqa: BLE001 - surface a clean message to the player
            raise RuntimeError(f"无法解码音频：{path}（{exc}）") from exc

        self._samples = decoded.samples  # array('h'), interleaved
        self._nch = decoded.nchannels
        self._sr = decoded.sample_rate
        self._duration = float(decoded.duration)
        self._total_samples = len(self._samples)
        self._pos = 0            # interleaved sample index of the playback head
        self._playing = False
        self._volume = 0.75
        self._anchor = time.monotonic()  # wall-clock timestamp of self._pos

        self._device = miniaudio.PlaybackDevice(
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=self._nch,
            sample_rate=self._sr,
            buffersize_msec=40,
        )
        self._gen = self._make_callback()
        next(self._gen)  # prime the generator before handing it to miniaudio
        self._device.start(self._gen)

    # -- callback generator (consumed by miniaudio's audio thread) ----------
    def _make_callback(self):
        want = yield b""  # prime point
        while not self._quit:
            chunk = self._produce(want)
            want = yield chunk

    def _produce(self, want):
        nch = self._nch
        n = max(1, int(want or 1024)) * nch
        now = time.monotonic()
        with self._lock:
            playing = self._playing
            pos = self._pos
            vol = self._volume
            total = self._total_samples

        silence = array.array("h", [0]) * n
        if not playing:
            with self._lock:
                self._anchor = now
            return silence

        remaining = total - pos
        if remaining <= 0:
            with self._lock:
                self._playing = False
                self._pos = total
                self._anchor = now
            return silence

        take = min(n, remaining)
        take -= take % nch  # keep whole frames
        if take <= 0:
            with self._lock:
                self._anchor = now
            return silence

        chunk = self._samples[pos : pos + take]
        if vol != 1.0:
            chunk = array.array("h", (int(s * vol) for s in chunk))

        if take < n:  # tail of the track: pad with silence to fill the period
            chunk.extend([0] * (n - take))
            with self._lock:
                self._playing = False
                self._pos = total
                self._anchor = now
        else:
            with self._lock:
                self._pos = pos + take
                self._anchor = now
        return chunk

    # -- player-facing surface ---------------------------------------------
    @property
    def state(self):
        with self._lock:
            pos = self._pos
            playing = self._playing
            anchor = self._anchor
        if playing:
            elapsed = time.monotonic() - anchor
            pos = min(self._total_samples, pos + int(elapsed * self._sr * self._nch))
        self.last = time.monotonic()
        return {
            "time": pos / (self._sr * self._nch),
            "duration": self._duration,
            "playing": playing,
        }

    def poll(self):
        return None  # alive; the player treats a non-None value as a crash

    def command(self, s: str):
        parts = s.split()
        cmd = parts[0] if parts else ""
        now = time.monotonic()
        with self._lock:
            if cmd == "play":
                self._playing = True
                self._anchor = now
            elif cmd == "pause":
                self._playing = False
                self._anchor = now
            elif cmd == "seek":
                t = float(parts[1]) if len(parts) > 1 else 0.0
                t = min(max(0.0, t), max(0.0, self._duration - 0.01))
                self._pos = int(t * self._sr) * self._nch
                self._pos -= self._pos % self._nch
                self._anchor = now
            elif cmd == "volume":
                self._volume = min(1.0, max(0.0, float(parts[1]) if len(parts) > 1 else 0.75))
            elif cmd == "quit":
                self._quit = True

    def close(self):
        self._quit = True
        with self._lock:
            self._playing = False
        for op in ("stop", "close"):
            try:
                getattr(self._device, op)()
            except Exception:
                pass
