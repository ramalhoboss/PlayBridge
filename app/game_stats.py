"""Your play, counted: each stretch a game ran on the PS5 while PlayBridge was connected (a session), and the trophies earned then, kept
on this PC, with the week, each game and each year worked out from them. The console's own total for each game (from its database)
stands beside PlayBridge's, since PlayBridge only sees the time it was connected.

The window tells the log once a second which game runs ('' for none or no connection). A session ends when another game starts, when
none runs, or when PlayBridge heard nothing for GAP seconds (it was closed or lost the console); one shorter than SHORTEST is left out."""
import json,os,time
from collections import defaultdict
from pathlib import Path

GAP=90;SHORTEST=60;SAVE_EVERY=60;KEEP=5000
DAY=86400
MONTHS=('January','February','March','April','May','June','July','August','September','October','November','December')

class PlayLog:
 def __init__(self,path,clock=time.time):
  self.path=Path(path);self.clock=clock;self.open=None;self.saved_at=0;self.sessions=[];self.trophies=[]
  try:data=json.loads(self.path.read_text(encoding='utf8'))
  except (OSError,ValueError):data={}
  if isinstance(data,dict):
   self.sessions=[list(item) for item in data.get('sessions',[]) if valid_session(item)]
   self.trophies=[list(item) for item in data.get('trophies',[]) if isinstance(item,list) and len(item)==4 and isinstance(item[2],(int,float))]
 def see(self,title,name='',now=None):
  now=self.clock() if now is None else now;open=self.open
  if open and (title!=open[0] or now-open[3]>GAP):self.finish()
  if title:
   if self.open is None:self.open=[title,name or title,now,now]
   else:self.open[3]=now;self.open[1]=name or self.open[1]
  if now-self.saved_at>=SAVE_EVERY:self.save(now)
 def finish(self):
  open,self.open=self.open,None
  if open and open[3]-open[2]>=SHORTEST:self.sessions.append(open);del self.sessions[:-KEEP]
 def trophy(self,title,name,count,now=None):self.trophies.append([title,name or title,self.clock() if now is None else now,int(count)]);del self.trophies[:-KEEP]
 def close(self):self.finish();self.save()
 def save(self,now=None):
  self.saved_at=self.clock() if now is None else now
  # The session still open is kept too, so a crash loses at most a minute of it.
  data=dict(sessions=self.all(),trophies=self.trophies)
  try:
   self.path.parent.mkdir(parents=True,exist_ok=True);spare=self.path.with_suffix('.tmp');spare.write_text(json.dumps(data,ensure_ascii=False),encoding='utf8');os.replace(spare,self.path)
  except OSError:pass
 def current(self):
  """The session still open, once it is long enough to count."""
  return self.open if self.open and self.open[3]-self.open[2]>=SHORTEST else None
 def all(self):return self.sessions+([self.open] if self.current() else [])

def valid_session(item):
 return isinstance(item,list) and len(item)==4 and isinstance(item[0],str) and all(isinstance(value,(int,float)) for value in item[2:]) and item[3]>=item[2]

def day_start(at):
 parts=time.localtime(at);return time.mktime((parts.tm_year,parts.tm_mon,parts.tm_mday,0,0,0,0,0,-1))

def split_days(start,end):
 """The seconds of a session on each day it touched: (day start, seconds)."""
 while start<end:
  day=day_start(start);next_day=day_start(day+DAY+3600)
  piece=min(end,next_day)-start
  yield day,piece;start+=piece

def hours(seconds):
 value=seconds/3600
 if value<1:return f'{round(seconds/60)} min'
 return f'{value:.1f} h' if value<10 else f'{round(value)} h'

def week(sessions,now):
 """The last seven days, today last: each day's name and hours, for the bars."""
 today=day_start(now);days=[day_start(today-DAY*back+3600) for back in range(6,-1,-1)];totals=defaultdict(float)
 for title,name,start,end in sessions:
  for day,seconds in split_days(start,end):totals[day]+=seconds
 most=max([totals[day] for day in days]+[1])
 return [dict(label='Today' if day==today else time.strftime('%a',time.localtime(day)),seconds=totals[day],text=hours(totals[day]) if totals[day] else '',share=totals[day]/most) for day in days]

def streak(sessions,now):
 """Days in a row with play, up to today (or yesterday, when today has none yet)."""
 played={day for title,name,start,end in sessions for day,_ in split_days(start,end)}
 day=day_start(now)
 if day not in played:day=day_start(day-DAY+3600)
 count=0
 while day in played:count+=1;day=day_start(day-DAY+3600)
 return count

def games(sessions,trophies,console_games,now):
 """Each game PlayBridge saw run, most played first, with the console's own total beside PlayBridge's."""
 seen=defaultdict(lambda:dict(seconds=0.0,sessions=0,longest=0.0,last=0.0,name='',week=0.0))
 week_start=day_start(now)-6*DAY
 for title,name,start,end in sessions:
  game=seen[title];length=end-start;game['seconds']+=length;game['sessions']+=1;game['longest']=max(game['longest'],length);game['last']=max(game['last'],end);game['name']=name or game['name'] or title
  game['week']+=sum(seconds for day,seconds in split_days(start,end) if day>=week_start)
 console={game.get('title'):game for game in console_games or []}
 earned=defaultdict(int);earned_week=defaultdict(int)
 for title,name,at,count in trophies:
  earned[title]+=count
  if at>=week_start:earned_week[title]+=count
 rows=[]
 for title,game in seen.items():
  total=(console.get(title) or {}).get('seconds')
  rows.append(dict(title=title,name=(console.get(title) or {}).get('name') or game['name'],seconds=game['seconds'],text=hours(game['seconds']),sessions=game['sessions'],
   average=hours(game['seconds']/max(1,game['sessions'])),longest=hours(game['longest']),last=game['last'],console=hours(total) if isinstance(total,(int,float)) and total>0 else '',
   week=game['week'],weekText=hours(game['week']) if game['week'] else '',trophies=earned[title],trophiesWeek=earned_week[title]))
 rows.sort(key=lambda row:(-row['seconds'],row['name'].lower()))
 most=max([row['seconds'] for row in rows]+[1])
 for row in rows:row['share']=row['seconds']/most
 return rows

def years(sessions):return sorted({time.localtime(start).tm_year for title,name,start,end in sessions},reverse=True)

def year(sessions,trophies,which,now):
 """One year in numbers: hours, days, sessions, the top games, the longest session, the busiest month and the trophies."""
 picked=[item for item in sessions if time.localtime(item[2]).tm_year==which]
 total=sum(end-start for _,_,start,end in picked);days={day for _,_,start,end in picked for day,_ in split_days(start,end)}
 by_game=defaultdict(float);names={};by_month=defaultdict(float)
 for title,name,start,end in picked:by_game[title]+=end-start;names[title]=name or title;by_month[time.localtime(start).tm_mon]+=end-start
 top=[dict(name=names[title],text=hours(seconds),share=seconds/max(by_game.values())) for title,seconds in sorted(by_game.items(),key=lambda item:-item[1])[:5]]
 longest=max(picked,key=lambda item:item[3]-item[2]) if picked else None
 month=max(by_month.items(),key=lambda item:item[1])[0] if by_month else None
 earned=sum(count for _,_,at,count in trophies if time.localtime(at).tm_year==which)
 return dict(year=which,hours=hours(total) if total else '0 h',days=len(days),sessions=len(picked),games=len(by_game),top=top,trophies=earned,
  longest=dict(name=longest[1],text=hours(longest[3]-longest[2]),when=time.strftime('%d %b',time.localtime(longest[2])).lstrip('0')) if longest else None,
  month=MONTHS[month-1] if month else '',soFar=which==time.localtime(now).tm_year)

def page(log,console_games,chosen_year,now):
 """What the Stats page shows."""
 sessions=log.all();trophies=log.trophies;week_bars=week(sessions,now);rows=games(sessions,trophies,console_games,now)
 week_seconds=sum(bar['seconds'] for bar in week_bars);week_start=day_start(now)-6*DAY
 known=years(sessions);which=chosen_year if chosen_year in known else (known[0] if known else time.localtime(now).tm_year)
 return dict(empty=not sessions,week=week_bars,weekText=hours(week_seconds) if week_seconds else '0 h',weekSessions=sum(1 for item in sessions if item[3]>=week_start),
  weekTrophies=sum(count for _,_,at,count in trophies if at>=week_start),streak=streak(sessions,now),games=rows[:40],years=known,year=year(sessions,trophies,which,now),
  playing=log.current()[1] if log.current() else '',playingText=hours(log.current()[3]-log.current()[2]) if log.current() else '')
