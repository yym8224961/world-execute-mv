#!/usr/bin/env python3
"""Windows 冒烟测试:音频时钟协议、渲染快照、播放循环与按键。

运行:uv run python tests/test_win_smoke.py -v
会短暂播放一段很轻的测试音(正弦波,音量已调低)。
"""
from __future__ import annotations
import io, json, math, os, struct, subprocess, sys, tempfile, time, unittest, wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def make_wav(path, seconds=45, rate=8000, amp=0.05):
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        frames = bytearray()
        for i in range(rate * seconds):
            v = int(amp * 32767 * math.sin(2 * math.pi * 440 * i / rate))
            frames += struct.pack('<h', v)
        w.writeframes(bytes(frames))


def read_state(proc, deadline=5.):
    end = time.monotonic() + deadline
    while time.monotonic() < end:
        if proc.poll() is not None:
            raise AssertionError(f'audio clock exited: {proc.stderr.read()}')
        line = proc.stdout.readline()
        if line:
            return json.loads(line)
    raise AssertionError('audio clock did not answer in time')


def wait_for(proc, predicate, desc, timeout=8.):
    end = time.monotonic() + timeout
    state = None
    while time.monotonic() < end:
        state = read_state(proc)
        if predicate(state):
            return state
    raise AssertionError(f'timeout waiting for {desc}; last={state}')


class TestAudioClock(unittest.TestCase):
    """audio_clock_win.py 必须说 AudioClock.swift 的协议。"""

    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp(prefix='mv-test-'))
        cls.wav = cls.dir / 'tone.wav'
        make_wav(cls.wav, seconds=30)

    @classmethod
    def tearDownClass(cls):
        cls.wav.unlink(missing_ok=True)

    def setUp(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(ROOT / 'audio_clock_win.py'), str(self.wav)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', bufsize=1)

    def tearDown(self):
        if self.proc.poll() is None:
            self.proc.stdin.write('quit\n'); self.proc.stdin.flush()
            try:self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:self.proc.kill()
        for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:pipe.close()
            except OSError:pass

    def send(self, s):
        self.proc.stdin.write(s + '\n'); self.proc.stdin.flush()

    def test_handshake_and_duration(self):
        state = read_state(self.proc)
        self.assertEqual(state['duration'], 30.0)
        self.assertFalse(state['playing'])
        self.assertEqual(state['time'], 0.0)

    def test_play_pause_seek_volume_quit(self):
        first = read_state(self.proc)
        self.send('volume 0.15')
        self.send('play')
        state = wait_for(self.proc, lambda s: s['playing'] and s['time'] > .3, 'playback start')
        self.assertTrue(state['playing'])
        self.send('pause')
        state = wait_for(self.proc, lambda s: not s['playing'], 'pause')
        t0 = state['time']
        time.sleep(.4)
        state = read_state(self.proc)
        self.assertFalse(state['playing'])
        self.assertLess(abs(state['time'] - t0), .15)
        self.send('seek 10')
        self.send('play')
        state = wait_for(self.proc, lambda s: s['time'] > 9.5, 'seek to 10s')
        self.assertLess(state['time'], 10.8)
        self.send('seek 999')
        state = wait_for(self.proc, lambda s: s['time'] >= 29.9, 'seek clamp to end')
        self.send('quit')
        self.proc.wait(timeout=5)
        self.assertEqual(self.proc.returncode, 0)

    def test_missing_file_fails_loudly(self):
        self.proc.kill(); self.proc.wait()
        proc = subprocess.Popen(
            [sys.executable, str(ROOT / 'audio_clock_win.py'), str(self.dir / 'nope.wav')],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8')
        _, err = proc.communicate(timeout=10)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('Audio error', err)


class TestRender(unittest.TestCase):
    """快照渲染:各时间点不崩、宽高正确、CJK 与 ANSI 正常。"""

    @classmethod
    def setUpClass(cls):
        from player import Film
        cls.film = Film()

    def test_frames(self):
        cases = [(0, 'A TERMINAL MUSIC VIDEO'), (8, 'READY'), (16.5, None),
                 (40, None), (130, '04 / EXECUTION'), (200, None)]
        for t, needle in cases:
            ready = needle in ('A TERMINAL MUSIC VIDEO', 'READY')
            c = self.film.render(t, 120, 40, paused=True, ready=ready)
            self.assertEqual(len(c.cells), 40, f'height at t={t}')
            self.assertEqual(len(c.cells[0]), 120, f'width at t={t}')
            text = c.plain()
            if needle:self.assertIn(needle, text)
            ansi = c.ansi()
            self.assertTrue(ansi.startswith('\x1b[H'), f'ansi at t={t}')
        small = self.film.render(10, 40, 12)
        self.assertIn('请放大窗口', small.plain())

    def test_captions_are_cjk(self):
        e = self.film.cue(30)
        if e:
            text = self.film.render(30, 120, 40).plain()
            self.assertIn(e['zh'][:4], text)

    def test_data_files_survive_gbk_locale(self):
        # 复现用户终端(中文 Windows,无 PYTHONUTF8):数据文件必须按 UTF-8 读。
        env = {k: v for k, v in os.environ.items() if k not in ('PYTHONUTF8', 'PYTHONIOENCODING')}
        env['PYTHONUTF8'] = '0'
        code = "import sys; sys.path.insert(0, '.'); from player import Film; Film(); print('LOCALE-OK')"
        proc = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True,
                              encoding='utf-8', env=env, cwd=str(ROOT))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('LOCALE-OK', proc.stdout)


class TestRunLoop(unittest.TestCase):
    """run() 主循环:子进程握手、渲染、右键快进、空格暂停、Q 退出。"""

    def run_player(self, argv, keys=()):
        import player
        saved = (sys.stdin, sys.stdout, player.msvcrt, player.setup_windows_console, player.windows_terminal_size)
        out = FakeOut()
        kb = FakeKeyboard(keys)
        player.msvcrt = kb
        player.setup_windows_console = lambda: None
        player.windows_terminal_size = lambda: (120, 40)
        sys.stdin = FakeIn()
        sys.stdout = out
        try:
            film = player.Film()
            player.run(player.build_arg_parser().parse_args(argv), film)
        finally:
            sys.stdin, sys.stdout, player.msvcrt, player.setup_windows_console, player.windows_terminal_size = saved
        return out

    def test_autoplay_seek_pause_quit(self):
        wav = Path(tempfile.mkdtemp(prefix='mv-test-')) / 'tone.wav'
        make_wav(wav, seconds=30)
        report = wav.parent / 'report.json'
        out = self.run_player(['--audio', str(wav), '--autoplay', '--stop-after', '8',
                               '--report', str(report)],
                              keys=[(.5, '\xe0M'), (1.0, ' '), (1.6, 'q')])
        self.assertIn('WORLD.EXECUTE(ME);', out.getvalue())
        self.assertIn('RUNNING', out.getvalue())
        self.assertIn('PAUSED', out.getvalue())
        self.assertIn('01 / CREATION', out.getvalue())
        data = json.loads(report.read_text(encoding='utf-8'))
        self.assertGreaterEqual(data['frames'], 24)
        times = [s['audio_time'] for s in data['samples']]
        self.assertTrue(any(4 <= t <= 7 for t in times), f'seek+5s not applied: {times}')
        self.assertLess(data['max_frame_render_seconds'], .5)

    def test_ready_screen_quit(self):
        wav = Path(tempfile.mkdtemp(prefix='mv-test-')) / 'tone.wav'
        make_wav(wav, seconds=10)
        out = self.run_player(['--audio', str(wav)], keys=[(.6, 'q')])
        self.assertIn('READY', out.getvalue())
        self.assertIn('A TERMINAL MUSIC VIDEO', out.getvalue())


class FakeIn:
    def isatty(self):return True
    def fileno(self):return 0


class FakeOut(io.StringIO):
    def isatty(self):return True
    def fileno(self):return 1
    def reconfigure(self, **k):pass


class FakeKeyboard:
    """把预设按键按时喂给 run() 的 msvcrt 替身。"""

    def __init__(self, schedule):
        self.events = [(time.monotonic() + t, s) for t, s in schedule]
        self.buf = []
    def kbhit(self):
        now = time.monotonic()
        while self.events and self.events[0][0] <= now:
            self.buf.extend(self.events.pop(0)[1])
        return bool(self.buf)
    def getwch(self):
        return self.buf.pop(0) if self.buf else '\x00'


if __name__ == '__main__':
    unittest.main(verbosity=2)
