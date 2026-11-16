"""Performance Lab: what the PS5's own counters and sensors measured for each game, gathered by game and mode from the session history
that performance.PerformanceLog keeps. A mode is the rate the game holds (30, 40, 60 or 120 fps) or Unlocked, so a game played in its
performance mode and its quality mode gives two reports."""
import time
from performance import CAPS,NEAR_RATE

def mode_of_summary(item):
 """The mode a kept summary ran in. Summaries kept before the mode was measured fall back to the rate the game held most of the time."""
 mode=item.get('mode')
 if isinstance(mode,str) and mode:return mode
 usual=item.get('fps_usual')
 if not isinstance(usual,(int,float)) or usual<1:return 'Unlocked'
 for cap in CAPS:
  if abs(usual-cap)<=NEAR_RATE:return f'{cap} fps'
 return 'Unlocked'

def number(value):
 return value if isinstance(value,(int,float)) and not isinstance(value,bool) else None

def weighted(items,key):
 """The average of key over the sessions that have it, each counted by its minutes."""
 pairs=[(number(item.get(key)),max(.1,number(item.get('minutes')) or .1)) for item in items]
 pairs=[(value,weight) for value,weight in pairs if value is not None]
 if not pairs:return None
 return round(sum(value*weight for value,weight in pairs)/sum(weight for _,weight in pairs),1)

def lowest(items,key):
 values=[number(item.get(key)) for item in items];values=[value for value in values if value is not None]
 return round(min(values),1) if values else None
def highest(items,key):
 values=[number(item.get(key)) for item in items];values=[value for value in values if value is not None]
 return max(values) if values else None

def duration(minutes):
 minutes=round(minutes or 0)
 if minutes<60:return f'{minutes} min'
 hours,rest=divmod(minutes,60);return f'{hours} h {rest} min' if rest else f'{hours} h'

def day(at):
 return time.strftime('%d %b %Y',time.localtime(at)).lstrip('0') if number(at) else ''

def reports(history):
 """The reports, newest played first: one for each game and mode, from the kept summaries that have a frame rate."""
 groups={}
 for item in history if isinstance(history,list) else []:
  if not isinstance(item,dict) or not item.get('title') or number(item.get('fps_average')) is None:continue
  groups.setdefault((item['title'],mode_of_summary(item)),[]).append(item)
 out=[]
 for (title,mode),items in groups.items():
  items.sort(key=lambda item:number(item.get('started')) or 0);latest=items[-1]
  minutes=sum(number(item.get('minutes')) or 0 for item in items)
  with_curve=[item for item in items if isinstance(item.get('curve'),list) and item['curve']]
  report=dict(key=f'{title}|{mode}',title=title,name=latest.get('name') or title,mode=mode,sessions=len(items),minutes=round(minutes,1),
   fps_average=weighted(items,'fps_average'),fps_low1=weighted(items,'fps_low1'),fps_low01=lowest(items,'fps_low01'),fps_lowest=lowest(items,'fps_lowest'),
   at_usual=weighted(items,'at_usual'),cpu_max=highest(items,'cpu_max'),soc_max=highest(items,'soc_max'),cpu_average=weighted(items,'cpu_average'),
   watts_average=weighted(items,'watts_average'),watts_max=highest(items,'watts_max'),last=number(latest.get('started')) or 0,
   curve=with_curve[-1]['curve'] if with_curve else [],curve_minutes=number(with_curve[-1].get('minutes')) if with_curve else None)
  out.append(report)
 out.sort(key=lambda report:-report['last'])
 return out

def stability(report):
 """How steadily the game held its mode, in words, or '' when it is unlocked or unknown."""
 share=report.get('at_usual')
 if report.get('mode')=='Unlocked' or share is None:return ''
 return f"{share:.0f}% of the time at {report['mode']}"

def row(report):
 """What the Performance Lab list shows for one report."""
 parts=[f"{report['fps_average']:.0f} fps average"]
 if report.get('fps_low1') is not None:parts.append(f"1% low {report['fps_low1']:.0f}")
 elif report.get('fps_lowest') is not None:parts.append(f"lowest {report['fps_lowest']:.0f}")
 if report.get('soc_max'):parts.append(f"SoC up to {report['soc_max']} °C")
 if report.get('watts_average') is not None:parts.append(f"{report['watts_average']:.0f} W")
 sessions=report['sessions']
 return dict(key=report['key'],name=report['name'],mode=report['mode'],numbers='  ·  '.join(parts),
  line=f"{sessions} {'session' if sessions==1 else 'sessions'}  ·  {duration(report['minutes'])}  ·  last played {day(report['last'])}",steady=stability(report))

def view(history,chosen=''):
 """The Performance Lab panel: the list, and the key of the report picked (the newest when none was or it is gone)."""
 found=reports(history);keys=[report['key'] for report in found]
 return dict(labRows=[row(report) for report in found][:40],labPicked=chosen if chosen in keys else (keys[0] if keys else ''))

def picked(history,key):
 """The report for key, or None."""
 return next((report for report in reports(history) if report['key']==key),None)
