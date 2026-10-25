"""Download the Riwayat database from Zenodo, verify it and unpack it (pure Python, any OS).
  python tools/get_data.py              # -> data/HadithMaster/hadith_master.db   (needs ~5.5 GB free: 0.6 GB archive + 4.7 GB database)
  python tools/get_data.py --dry-run    # only check that the Zenodo file is reachable
  python tools/get_data.py --keep       # keep the .xz archive after unpacking
DOI: 10.5281/zenodo.23630500 (all versions); this script pins version v1 (10.5281/zenodo.23630501)."""
import sys, os, hashlib, lzma, urllib.request, pathlib
URL = 'https://zenodo.org/records/23630501/files/hadith_master.db.xz?download=1'
SIZE = 576781988
MD5 = '3f215d451a6534ea648ee548cf38045e'
SHA256 = '0519e097f742b2d9262a1a6c05e7cb0d697f0bef71179c1610f9d28445dfde05'
dest = pathlib.Path(__file__).resolve().parent.parent / 'data' / 'HadithMaster'
arc, db = dest / 'hadith_master.db.xz', dest / 'hadith_master.db'
req = urllib.request.Request(URL, method='HEAD')
with urllib.request.urlopen(req, timeout=60) as r:
    n = int(r.headers.get('Content-Length', 0)); print('Zenodo file reachable,', n, 'bytes (expected', SIZE, ')')
    if n != SIZE: sys.exit('size mismatch: the record may have changed; check https://doi.org/10.5281/zenodo.23630500')
if '--dry-run' in sys.argv: sys.exit(0)
if db.exists(): sys.exit(f'{db} already exists; remove it first if you want to replace it')
dest.mkdir(parents=True, exist_ok=True)
have = arc.stat().st_size if arc.exists() else 0
if have != SIZE:                                   # resume a partial download
    rq = urllib.request.Request(URL, headers={'Range': f'bytes={have}-'} if have else {})
    with urllib.request.urlopen(rq, timeout=60) as r, open(arc, 'ab' if have and r.status == 206 else 'wb') as f:
        done = have if r.status == 206 else 0
        while True:
            b = r.read(1 << 20)
            if not b: break
            f.write(b); done += len(b); print(f'\r{done / 1e6:7.1f} / {SIZE / 1e6:.1f} MB', end='', flush=True)
    print()
m, s = hashlib.md5(), hashlib.sha256()
with open(arc, 'rb') as f:
    for b in iter(lambda: f.read(1 << 20), b''): m.update(b); s.update(b)
if m.hexdigest() != MD5 or s.hexdigest() != SHA256: sys.exit('checksum mismatch: delete the archive and run again')
print('checksums OK; unpacking (this takes a few minutes)...')
with lzma.open(arc, 'rb') as src, open(db, 'wb') as out:
    while True:
        b = src.read(1 << 22)
        if not b: break
        out.write(b)
if '--keep' not in sys.argv: arc.unlink()
print('done:', db, f'({db.stat().st_size / 1e9:.2f} GB). Check it with: python tools/verify_db.py')
