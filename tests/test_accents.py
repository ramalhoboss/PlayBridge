import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import accents

INK='#101010';PAGE='#141414';ONLINE='#5BE38C'

class AccentTests(unittest.TestCase):
 def test_every_accent_reads_well_both_ways(self):
  for name,(main,soft,hover) in accents.ACCENTS.items():
   with self.subTest(name):
    # Dark text on a button in the accent, and the accent's words on a dark card.
    self.assertGreaterEqual(accents.contrast(INK,main),7,name);self.assertGreaterEqual(accents.contrast(INK,hover),7,name)
    self.assertGreaterEqual(accents.contrast(main,PAGE),4.5,name);self.assertGreaterEqual(accents.contrast(soft,PAGE),7,name)
 def test_no_accent_is_the_online_green(self):
  def rgb(code):return [int(code[i:i+2],16) for i in (1,3,5)]
  for name,(main,_,_) in accents.ACCENTS.items():
   self.assertGreater(sum(abs(a-b) for a,b in zip(rgb(main),rgb(ONLINE))),120,name)
 def test_unknown_names_fall_back(self):
  self.assertEqual(accents.accent('Nope'),accents.ACCENTS['Gold']);self.assertEqual(accents.shade('Nope'),0.0);self.assertEqual(accents.shade('Darkest'),0.7)
 def test_gold_leaves_the_classic_colours_alone(self):
  import luxury_theme,scene
  before=(luxury_theme.GOLD,scene.GOLD,luxury_theme.GOLD_HOVER)
  accents.apply_classic('Gold');accents.apply_classic('Nope');self.assertEqual((luxury_theme.GOLD,scene.GOLD,luxury_theme.GOLD_HOVER),before)
  try:
   accents.apply_classic('Sky');self.assertEqual((luxury_theme.GOLD,scene.GOLD),('#5FA8FF','#5FA8FF'))
  finally:luxury_theme.GOLD,scene.GOLD,luxury_theme.GOLD_HOVER=before;scene.GOLD_HOVER=before[2]

if __name__=='__main__':unittest.main()
