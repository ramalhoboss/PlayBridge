"""Trophy guides: choosing a trophy in the trophy list opens a web search for how to earn it, in this PC's own browser.

Nothing is read from the guide sites and nothing is sent but the search itself, which carries only the game's and the trophy's names.
A trophy whose name the PC does not know (the PS5 keeps some hidden until they are earned) searches for the game's whole guide."""
import re
from urllib.parse import quote_plus

SEARCH='https://duckduckgo.com/?q='
# Marks that game names carry and searches do better without.
MARKS=re.compile('[™®©]')

def plain(text):
 """A name without trademark marks and extra spaces."""
 return ' '.join(MARKS.sub(' ',str(text or '')).split())

def guide_query(game,trophy=None):
 """What is searched for: the trophy's guide, or the game's when there is no trophy or no name for it."""
 game=plain(game) or 'PS5';name=plain((trophy or {}).get('name'))
 return f'{game} {name} trophy guide' if name else f'{game} trophy guide'

def guide_url(game,trophy=None):
 return SEARCH+quote_plus(guide_query(game,trophy))

def guide_line(game,trophy=None):
 """What the window says once the guide is open."""
 name=plain((trophy or {}).get('name'));return f'Opened a guide for {name} in your browser.' if name else f'Opened the trophy guide for {plain(game) or "the game"} in your browser.'
