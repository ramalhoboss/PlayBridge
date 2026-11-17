"""Search in Settings. The index is read from SettingsPage.qml itself, so every card, switch and note is found by its own words and
a new setting needs nothing added here: each Card's title, the section it shows in, and the plain words of what it holds."""
import re

STRING=re.compile(r'"((?:[^"\\]|\\.)*)"')
WORDS=re.compile(r"[a-z0-9][a-z0-9'+.-]*")

def blocks(text,opening='Card {'):
 """The text of each block that starts with opening, up to its matching brace; braces inside quotes do not count."""
 found=[];at=0
 while True:
  start=text.find(opening,at)
  if start<0:return found
  depth=0;quoted=False;i=start+len(opening)-1
  while i<len(text):
   c=text[i]
   if quoted:
    if c=='\\':i+=1
    elif c=='"':quoted=False
   elif c=='"':quoted=True
   elif c=='{':depth+=1
   elif c=='}':
    depth-=1
    if depth==0:break
   i+=1
  found.append(text[start:i+1]);at=i+1

def index(qml,sections):
 """[dict(section, title, words)] for each card; sections: [(key, label, note)]. Cards with no fixed title take their section's name."""
 labels={key:label for key,label,_ in sections};cards=[]
 for block in blocks(qml):
  where=re.search(r'visible:\s*page\.s\.section\s*===\s*"(\w+)"',block)
  if not where or where.group(1) not in labels:continue
  title=re.search(r'^\s*title:\s*"([^"]+)"\s*$',block,re.M)
  texts=[part.replace('\\n',' ').replace('\\"','"') for part in STRING.findall(block)]
  # Words people read: anything with a space or a capital, not ids, colours or the section key.
  words=[t for t in texts if re.search(r'[A-Za-z]{3}',t) and (' ' in t or t[:1].isupper()) and not t.startswith('#')]
  cards.append(dict(section=where.group(1),label=labels[where.group(1)],title=title.group(1) if title else labels[where.group(1)],words=words))
 return cards

def search(cards,query,limit=8):
 """The cards that hold every word of query, best first: words in the title, then in the section's name, then anywhere."""
 terms=WORDS.findall(query.lower())
 if not terms:return []
 hits=[]
 for card in cards:
  title=card['title'].lower();label=card['label'].lower();body=' '.join(card['words']).lower()
  if not all(term in title or term in label or term in body for term in terms):continue
  score=sum(3 if term in title else 2 if term in label else 1 for term in terms)
  # The words together, as written on a switch or a note, count most.
  phrase=' '.join(terms)
  if len(terms)>1 and (phrase in title or phrase in body):score+=5
  hits.append((-score,len(hits),dict(section=card['section'],label=card['label'],title=card['title'],snippet=snippet(card['words'],terms,card['title']))))
 return [hit for _,_,hit in sorted(hits)[:limit]]

def snippet(words,terms,title='',width=90):
 """The words around the first match outside the title, cut at spaces to about width characters."""
 for text in words:
  low=text.lower();at=min((low.find(term) for term in terms if term in low),default=-1)
  if at<0 or text==title:continue
  start=0
  if at>30:start=text.find(' ',at-30)+1 or at
  end=len(text) if len(text)-start<=width else text.rfind(' ',start,start+width)
  if end<=start:end=start+width
  return ('…' if start else '')+text[start:end].strip()+('…' if end<len(text) else '')
 return ''
