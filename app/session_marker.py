"""Whether PlayBridge closed normally last time. While it is open, a small file says so, with the page it is on; a normal close
removes it. Found at the next start, it means the last session ended some other way: a crash, a power cut or Task Manager."""
import json,os,time
from pathlib import Path

NAME='open.json'

def begin(folder,version):
 """Starts this session's marker. Returns what the last one left, when it did not close normally, or None."""
 path=Path(folder)/NAME;left=None
 try:
  data=json.loads(path.read_text(encoding='utf8'))
  if isinstance(data,dict):left=data
 except (OSError,ValueError):pass
 write(path,dict(pid=os.getpid(),started=time.time(),version=version,page=''))
 return left

def write(path,data):
 try:Path(path).write_text(json.dumps(data),encoding='utf8')
 except OSError:pass

def page(folder,name):
 """Notes the page shown now, for opening on it again after a crash."""
 path=Path(folder)/NAME
 try:data=json.loads(path.read_text(encoding='utf8'))
 except (OSError,ValueError):return
 if isinstance(data,dict) and data.get('page')!=name:data['page']=name;write(path,data)

def end(folder):
 try:(Path(folder)/NAME).unlink(missing_ok=True)
 except OSError:pass
