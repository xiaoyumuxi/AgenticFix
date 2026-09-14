"""Read-only Docker probes against the base, official fix and both candidate patches.
Requires the verification image retained by the measured runs (or rebuilding their Dockerfile).
"""
import asyncio
import hashlib
import json
from pathlib import Path

from sandbox.docker import DockerSandbox
from workspace.repository import WorkspaceManager, git

ROOT=Path(__file__).resolve().parents[3]
PROBE='''import json
from decimal import Decimal
from fractions import Fraction
from more_itertools import numeric_range
cases=[(0,), (3,3), (2,1), (1,2,-1), (0.0,), (Decimal('0'),), (Fraction(0),),
       (5,), (1,6,2), (5,0,-2), (0,1,0.25),
       (Decimal('0'),Decimal('1'),Decimal('0.25')),
       (Fraction(0),Fraction(1),Fraction(1,4)), (4,)]
rows=[]
for args in cases:
    value=numeric_range(*args)
    expected=list(value)[::-1]
    row={'args':repr(args),'expected':repr(expected)}
    try:
        actual=list(reversed(value))
        row.update(actual=repr(actual),passed=actual==expected)
        if args==(4,):
            row['forward_after']=repr(list(value))
            row['second_reverse']=repr(list(reversed(value)))
    except Exception as exc:
        row.update(actual=type(exc).__name__,passed=False)
    rows.append(row)
print(json.dumps(rows))
'''

async def main():
    before='247e15b3a489d5805375c95dfa79486c9bd0eb1b'
    manager=WorkspaceManager(ROOT/'.cache/repositories',ROOT/'.worktrees')
    repo=manager.prepare_repository(str(ROOT/'.cache/m3-upstream'),before)
    work=manager.create_workspace(repo,'probe-1152-run011')
    sandbox=DockerSandbox(ROOT/'runs/m3-development/issue-probe-run011')
    summary=json.loads((ROOT/'docs/iteration-evidence/RUN-20260914-011/summary.json').read_text())
    sandbox.image_id=summary['rebuild']['image_id']
    rows={}
    try:
        for name,patch in [('before',None),('official','RUN-20260914-011/official-source.patch'),('v8','RUN-20260914-011/candidate.patch')]:
            git(work.path,'restore','--source',before,'--','.')
            if patch:
                git(work.path,'apply',str(ROOT/'docs/iteration-evidence'/patch))
            result=await sandbox.run(('python','-c',PROBE),work.path,30)
            assert result.exit_code==0,result.stderr
            rows[name]=json.loads(result.stdout)
        assert sum(not r['passed'] for r in rows['before'])==7
        assert all(r['passed'] for name in ['official','v8'] for r in rows[name])
        Path(__file__).with_name('results-v8.json').write_text(json.dumps({
            'kind':'Supplemental Docker value probes, separate from original pytest runs',
            'base_commit':before,'image_id':sandbox.image_id,'rows':rows,
            'probe_sha256':hashlib.sha256(PROBE.encode()).hexdigest(),
        },indent=2)+'\n')
    finally:
        manager.cleanup_workspace(work)

if __name__=='__main__':
    asyncio.run(main())
