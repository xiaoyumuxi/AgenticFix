"""Controlled interventions for the stale-bytecode defect; run from the repository root."""
import asyncio
import hashlib
import importlib.util
import json
import os
import platform
import py_compile
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OLD = 'ba96c26cb61efff5ba05105e07218b9aaa240940'
FIXED = '30cfc421c6a7850411ba4fa72bfd3f9df5cabbf6'

async def main():
    results = []
    variants = ['old', 'old_no_write', 'old_remove_cache', 'old_change_mtime',
                'old_change_size', 'fixed']
    for variant in variants:
        commit = FIXED if variant == 'fixed' else OLD
        with tempfile.TemporaryDirectory(prefix='bytecode-diagnose-') as directory:
            root = Path(directory)
            implementation = root / 'historical.py'
            code = subprocess.check_output(['git', 'show', f'{commit}:sandbox/local.py'], cwd=ROOT)
            implementation.write_bytes(code)
            spec = importlib.util.spec_from_file_location('historical', implementation)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            fixture = root / 'fixture'
            fixture.mkdir()
            source = fixture / 'example.py'
            source.write_bytes(b'value = 1\n')
            stamp = 1700000000
            os.utime(source, (stamp, stamp))
            cache = Path(py_compile.compile(str(source), doraise=True))
            header = cache.read_bytes()[:16]
            flags, cache_time, cache_size = struct.unpack('<III', header[4:16])
            source.write_bytes(b'value = 2\n' if variant != 'old_change_size'
                               else b'value = 2 # changed size\n')
            os.utime(source, (stamp, stamp + 2 if variant == 'old_change_mtime' else stamp))
            if variant == 'old_remove_cache':
                cache.unlink()
            args = [sys.executable]
            if variant == 'old_no_write':
                args.append('-B')
            args.extend(['-c', 'import example; print(example.value); assert example.value == 2'])
            source_stat = source.stat()
            result = await module.LocalSandbox(trusted=True, max_output_bytes=2000).run(
                tuple(args), fixture, 10)
            results.append({'variant':variant, 'agent_commit':commit,
                'implementation_sha256':hashlib.sha256(code).hexdigest(),
                'source_text':source.read_text(), 'source_size':source_stat.st_size,
                'source_mtime_seconds':int(source_stat.st_mtime),
                'original_cache_header':{'flags':flags,'mtime_seconds':cache_time,'size':cache_size},
                'cache_present_before_execution':variant != 'old_remove_cache',
                'stdout':result.stdout.strip(),'exit_code':result.exit_code})
    assert [r['stdout'] for r in results] == ['1','1','2','2','2','2']
    assert [r['exit_code'] for r in results] == [1,1,0,0,0,0]
    print(json.dumps({'python':platform.python_version(),'platform':platform.platform(),
                     'cases':results},ensure_ascii=False,indent=2))

asyncio.run(main())
