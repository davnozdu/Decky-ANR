"""Explicit public allowlist: never pick up user-imported or private AMD DLLs."""
from pathlib import Path
import hashlib
import io
import os
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'out'
OUT.mkdir(exist_ok=True)
version = os.environ.get('ANR_VERSION', 'V.B16')

def check_zip(data, depth=0):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert z.testzip() is None
        for item in z.infolist():
            name = item.filename.replace('\\', '/').lower()
            assert not any(p in name.split('/') for p in ('private', 'local-fsr4', 'fsr4-libraries', 'fsr4-archives', 'lsfg-library')), name
            assert Path(name).name not in ('amdxcffx64.dll', 'amdvkffx64.dll', 'lsfg-vk.dll', 'lossless.dll'), name
            if name.endswith('.zip'):
                assert depth < 4
                check_zip(z.read(item), depth + 1)

plugin = OUT / 'Decky.FrameGen.Hub.zip'
files = [ROOT / n for n in ('main.py', 'plugin.json', 'package.json', 'LICENSE', 'README.md', 'README.ru.md', 'FSR4-EXTRACTION.md', 'dist/index.js')]
files += sorted((ROOT / 'py_modules').glob('*.py'))
files += [p for p in (ROOT / 'licenses').rglob('*') if p.is_file()]
files += [ROOT / 'bin' / f'anr-fg-{version}-{kind}.zip' for kind in ('full', 'addon')]
with zipfile.ZipFile(plugin, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, 'Decky FrameGen Hub/' + str(p.relative_to(ROOT)))
extractor = OUT / 'FSR4-Extractor.zip'
with zipfile.ZipFile(extractor, 'w', zipfile.ZIP_DEFLATED) as z:
    for name in ('tools/extract-fsr4.py', 'tools/extract-fsr4.sh', 'tools/extract-fsr4.cmd', 'py_modules/fsr4.py', 'py_modules/fsr4_extract.py', 'FSR4-EXTRACTION.md', 'LICENSE'):
        z.write(ROOT / name, 'FSR4-Extractor/' + name)
for path in (plugin, extractor):
    check_zip(path.read_bytes())
    print(f'{path}: {path.stat().st_size} bytes; no AMD/LS DLLs (nested archives checked)')
(OUT / 'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in (plugin, extractor)))
