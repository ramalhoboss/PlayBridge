import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import settings_search

SECTIONS=(('console','Console',''),('picture','Picture',''),('captures','Captures',''),('sound','Sound',''),('live','Streaming',''),
 ('connect','Connections',''),('look','Appearance',''),('phone','Phone',''),('updates','Updates',''))
SAMPLE='''
Card {
    title: "Go live"
    visible: page.s.section === "live"
    Caption { text: "Stream key" }
    Note { text: "Brace } inside words, and a \\"quote\\"." }
    property var a: ({})
}
Card {
    title: "Stream Deck and OBS"
    visible: page.s.section === "connect"
    Note { text: "Each address starts with a secret key made on this PC." }
}
Card {
    title: "Hidden"
    visible: page.s.section === "nowhere"
}
'''

class SettingsSearchTests(unittest.TestCase):
 def test_cards_are_read_with_their_section_and_words(self):
  cards=settings_search.index(SAMPLE,SECTIONS)
  self.assertEqual([(c['section'],c['title']) for c in cards],[('live','Go live'),('connect','Stream Deck and OBS')])
  self.assertIn('Stream key',cards[0]['words']);self.assertIn('Brace } inside words, and a "quote".',cards[0]['words'])
 def test_words_written_together_come_first(self):
  hits=settings_search.search(settings_search.index(SAMPLE,SECTIONS),'stream key')
  self.assertEqual([h['title'] for h in hits],['Go live','Stream Deck and OBS']);self.assertEqual(hits[0]['label'],'Streaming')
  self.assertEqual(hits[0]['snippet'],'Stream key')
  self.assertEqual(settings_search.search(settings_search.index(SAMPLE,SECTIONS),'  '),[])
  self.assertEqual(settings_search.search(settings_search.index(SAMPLE,SECTIONS),'xyz'),[])
 def test_snippets_cut_at_spaces(self):
  text='The PS5 answers only this PC and nothing else, which keeps every stream between the console and this computer private.'
  cut=settings_search.snippet([text],['computer'],width=40)
  self.assertTrue(cut.startswith('…') and cut.endswith('…') or cut.endswith('private.'));self.assertIn('computer',cut)
  self.assertLessEqual(len(cut),42)
 def test_the_real_settings_page_finds_what_people_look_for(self):
  cards=settings_search.index((ROOT/'app'/'qml'/'SettingsPage.qml').read_text(encoding='utf8'),SECTIONS)
  self.assertGreater(len(cards),30)
  for query,title in (('fan','PS5 fans'),('away','Away from home'),('microphone','Microphone'),('qr','Pairing'),('go back','Updates'),
   ('hdr','Picture Studio'),('stream key','Go live'),('check setup','Check setup'),('webhook','Discord channel')):
   hits=settings_search.search(cards,query)
   self.assertTrue(hits,query);self.assertEqual(hits[0]['title'],title,query)

if __name__=='__main__':unittest.main()
