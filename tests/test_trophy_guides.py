"""Trophy guides: the search carries only the game's and the trophy's names, without trademark marks; a trophy without a known name
searches for the game's guide; Enter on the trophy list opens the chosen trophy's guide and nothing else changes."""
import sys,unittest
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import trophy_guides as tg
from test_qt_models import shelf

def searched(url):
 parts=urlsplit(url);return parts.netloc,parse_qs(parts.query)['q'][0]

class TrophyGuideTests(unittest.TestCase):
 def test_the_search_has_the_names_and_nothing_else(self):
  host,query=searched(tg.guide_url("Demon's Souls™",dict(id=3,name='  Penetrator  Slayer ',grade='gold')))
  self.assertEqual((host,query),('duckduckgo.com',"Demon's Souls Penetrator Slayer trophy guide"))
  self.assertEqual(tg.guide_line("Demon's Souls",dict(name='Penetrator Slayer')),'Opened a guide for Penetrator Slayer in your browser.')
 def test_missable_trophies_of_a_game(self):
  self.assertEqual(searched(tg.missable_url('Uncharted™ 4'))[1],'Uncharted 4 missable trophies');self.assertEqual(searched(tg.missable_url(''))[1],'PS5 missable trophies')
 def test_a_trophy_without_a_name_searches_for_the_game(self):
  self.assertEqual(searched(tg.guide_url('Astro Bot®',dict(id=12,name='')))[1],'Astro Bot trophy guide')
  self.assertEqual(searched(tg.guide_url('',None))[1],'PS5 trophy guide')
  self.assertEqual(tg.guide_line('Astro Bot',dict(name='')),'Opened the trophy guide for Astro Bot in your browser.')
 def test_enter_on_the_list_opens_the_chosen_trophy(self):
  page,sounds,ran,_=shelf();page.actions['trophy_guide']=lambda *values:ran.append(('trophy_guide',)+values)
  page.link.game_name=lambda title:{'PPSA00001':'Zeta'}.get(title,title)
  page.link.sets['PPSA00001']=dict(name='Zeta Trophies',trophies=[dict(id=n,name=f'Step {n}') for n in range(3)])
  page.open_menu('more');page.menu_choose([key for key,_ in page.menu['items']].index('trophies'));page.navigate('down')
  page.navigate('accept');self.assertEqual(ran[-1],('trophy_guide','Zeta',dict(id=1,name='Step 1')));self.assertEqual(sounds[-1],'accept')
  self.assertEqual(page.panel,dict(title='PPSA00001',selected=1),'the list stays open on the same trophy')
 def test_an_empty_list_has_no_guide(self):
  page,sounds,ran,_=shelf();page.link.sets['PPSA00001']=dict(trophies=[]);page.panel=dict(title='PPSA00001',selected=0)
  page.navigate('accept');self.assertEqual(sounds[-1],'edge');self.assertFalse(any(item[0]=='trophy_guide' for item in ran))

if __name__=='__main__':unittest.main()
