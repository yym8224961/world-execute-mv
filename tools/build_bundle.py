"""Build a single-file macOS player containing the original music and scenes."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipapp
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ('player.py', 'scenes.py', 'audio-clock', 'config.json', 'lyrics.json',
         'spectrum.json', 'media/song.mp3')


def main():
    if not (ROOT/'media/song.mp3').is_file():
        raise SystemExit('请先将本地音频放入 media/song.mp3；音频不会提交到仓库。')
    subprocess.run(['/bin/zsh', str(ROOT/'build-audio.sh'), '--universal'], check=True)
    output = ROOT/'dist'
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='bundle-', dir=ROOT/'.build') as folder:
        stage = Path(folder)
        manifest = {'format': 1, 'platform': 'macOS 12+', 'architectures': ['arm64', 'x86_64'], 'files': {}}
        for name in FILES:
            data = (ROOT/name).read_bytes()
            target = stage/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            manifest['files'][name] = hashlib.sha256(data).hexdigest()
        (stage/'__main__.py').write_bytes((ROOT/'tools/bundle_main.py').read_bytes())
        (stage/'bundle-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
        package = output/'world-execute-mv.pyz'
        zipapp.create_archive(stage, package, interpreter='/usr/bin/env python3', compressed=True)
        package.chmod(0o755)
    # A small convenient download with the single-file player and instructions.
    with zipfile.ZipFile(output/'world-execute-mv-macos.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, path in [('world-execute-mv.pyz', package), ('README.md', ROOT/'README.md'),
                           ('运行单文件.command', ROOT/'运行单文件.command'),
                           ('docs/images/mv-cover.png', ROOT/'docs/images/mv-cover.png')]:
            archive.write(path, 'world-execute-mv/'+name)
    paths = [package, output/'world-execute-mv-macos.zip']
    (output/'SHA256SUMS.txt').write_text(''.join(
        hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in paths), encoding='utf-8')
    print(json.dumps({'artifacts': [str(p) for p in paths], 'embedded_audio': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
