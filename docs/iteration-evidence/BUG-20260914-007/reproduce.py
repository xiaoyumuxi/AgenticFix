import asyncio,json,tempfile,subprocess,hashlib
from pathlib import Path
from types import SimpleNamespace
from config import Settings
from sandbox.docker import DockerSandbox
from agent.loop import AgentLoop
from tools.base import ToolResult

ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'runs/environment-feedback-replay';OUT.mkdir(parents=True,exist_ok=True)
OLD='2fd3229a08f279671745180699a3b135969e9347'
old={};exec(compile(subprocess.check_output(['git','show',OLD+':agent/loop.py']),'<historical agent loop>','exec'),old)
settings=Settings(_env_file=None)
obj=SimpleNamespace(settings=settings)
def compare(result):
 before=old['AgentLoop'].tool_message(obj,result,'build_environment')
 after=AgentLoop.tool_message(obj,result,'build_environment')
 return {'before':json.loads(before),'after':json.loads(after),'metrics':{
  'before_message_chars':len(before),'after_message_chars':len(after),
  'before_has_cause':'No module named' in before,'after_has_cause':'No module named' in after,
  'before_has_exit_code':'exit_code' in before,'after_has_exit_code':'exit_code' in after}}
async def main():
 synthetic=ToolResult(success=False,error_code='ENVIRONMENT_BUILD_FAILED',data={
  'stdout':'','stderr':'Downloading build layers...\n'*600+"ModuleNotFoundError: No module named 'agenticfix_missing_dependency'\n",
  'exit_code':1,'timed_out':False,'artifact':'synthetic.json'})
 rows={'kind':'Engineering feedback probes; no model request, not a real issue attempt','old_agent_commit':OLD,'synthetic':compare(synthetic)}
 sandbox=DockerSandbox(OUT/'docker',max_output_bytes=20000)
 dockerfile="FROM python:3.12-slim\nRUN python -c \"print('setup-start'); print('download-progress-' * 2500); import agenticfix_missing_dependency\"\n"
 (OUT/'Dockerfile').write_text(dockerfile)
 with tempfile.TemporaryDirectory() as temp:
  result=await sandbox.build(dockerfile,Path(temp),300)
  data=result.model_dump() | sandbox.last_build
  (OUT/'build-result.json').write_text(json.dumps(data,indent=2)+'\n')
  tool=ToolResult(success=False,error_code='ENVIRONMENT_BUILD_FAILED',data=data)
  rows['docker']=compare(tool)
  rows['docker']['raw_has_cause']='No module named' in result.stderr
  rows['docker']['diagnostic_lines']=result.diagnostic_lines
  rows['docker']['comparison_scope']='Same newly captured Docker result through old/new model projection; not old Docker collector execution'
  assert result.exit_code != 0 and not result.timed_out
  assert any('No module named' in line for line in result.diagnostic_lines)
  assert rows['docker']['metrics']['after_has_cause']
  assert rows['synthetic']['metrics']['after_has_cause']
  assert not rows['synthetic']['metrics']['before_has_cause']
 (OUT/'comparison.json').write_text(json.dumps(rows,indent=2)+'\n')
 print(json.dumps({key:rows[key]['metrics'] for key in ['synthetic','docker']},indent=2))
asyncio.run(main())
