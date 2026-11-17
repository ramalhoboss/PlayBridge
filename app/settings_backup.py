"""Settings › Updates › Your settings: PlayBridge's settings saved in one file, and put back from one, on this PC or another.

Sign-ins, stream keys and keys stay out of the file: they are encrypted for this Windows account and would not open anywhere else.
So does what belongs to this PC alone, such as away play's state. Putting a file back keeps this PC's own sign-ins and keys."""
import json,time
from pathlib import Path

KIND='PlayBridge settings'
LEFT_OUT=frozenset({'pairing_key','psn_token','psn_until','discord_webhook','api_secret','api_port','phone_tokens','live_key','away',
 'setup_checked','update_offered','play_limit'})
LARGEST=2_000_000

def portable(settings):
 """The settings that may leave this PC: no secrets, and stream services without their keys."""
 kept={key:value for key,value in settings.items() if key not in LEFT_OUT}
 if isinstance(kept.get('live_targets'),dict):
  kept['live_targets']={service:dict(key='',server=str(item.get('server','')) if isinstance(item,dict) else '') for service,item in kept['live_targets'].items()}
 return kept

def write(path,settings,version,now=None):
 data=dict(kind=KIND,version=version,saved=time.strftime('%Y-%m-%d %H:%M',time.localtime(now)),settings=portable(settings))
 Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf8')
 return len(data['settings'])

def read(path):
 """The settings a backup holds. ValueError says in a few words why a file is not one."""
 path=Path(path)
 if path.stat().st_size>LARGEST:raise ValueError('that file is too large to be a PlayBridge backup')
 try:data=json.loads(path.read_text(encoding='utf8'))
 except (UnicodeDecodeError,json.JSONDecodeError):raise ValueError('that file is not a PlayBridge backup') from None
 if not isinstance(data,dict) or data.get('kind')!=KIND or not isinstance(data.get('settings'),dict):raise ValueError('that file is not a PlayBridge backup')
 return portable(data['settings'])

def restore(current,incoming):
 """This PC's settings with a backup's put over them. Secrets and this PC's own state stay as they are, and so do the stream keys
 of services the backup also names."""
 merged=dict(current)
 for key,value in portable(incoming).items():
  if key=='live_targets' and isinstance(value,dict):
   mine=current.get('live_targets') if isinstance(current.get('live_targets'),dict) else {}
   targets=dict(mine)
   for service,item in value.items():
    targets[service]=dict(key=(mine.get(service) or {}).get('key','') if isinstance(mine.get(service),dict) else '',server=item.get('server',''))
   merged['live_targets']=targets
  else:merged[key]=value
 return merged
