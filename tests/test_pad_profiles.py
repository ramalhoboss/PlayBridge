"""Controller profiles: buttons trade places together, shoulders and triggers swap with their pull, sticks swap and invert, turbo
repeats only while held, one hand works with the shoulder held, and each game keeps its own profile apart from the one for every game."""
import shutil,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import pad_profiles as pp
from pad_input import CROSS,CIRCLE,SQUARE,TRIANGLE,L1,L2,R1,R2,UP,LEFT,PadState,NEUTRAL

def profile(**changes):return pp.clean(dict(pp.DEFAULT,**changes))

class PadProfileTests(unittest.TestCase):
 def test_nothing_changes_without_a_profile(self):
  state=PadState(buttons=CROSS,lx=10,ry=200);self.assertIs(pp.apply(pp.clean({}),state,0),state);self.assertIs(pp.apply(None,state,0),state)
 def test_buttons_trade_places_together(self):
  self.assertEqual(pp.apply(profile(swap_face=True),PadState(buttons=CROSS),0).buttons,CIRCLE)
  self.assertEqual(pp.apply(profile(swap_face=True),PadState(buttons=CROSS|CIRCLE),0).buttons,CROSS|CIRCLE)
  self.assertEqual(pp.apply(profile(remap=[['l1','cross'],['square','triangle']]),PadState(buttons=L1|SQUARE),0).buttons,CROSS|TRIANGLE)
 def test_shoulders_and_triggers_swap_with_their_pull(self):
  state=pp.apply(profile(swap_shoulders=True),PadState(buttons=L1|R2,r2=255),0);self.assertEqual((state.buttons,state.l2,state.r2),(L2|R1,255,0))
 def test_sticks_swap_and_invert(self):
  state=pp.apply(profile(swap_sticks=True,invert_ry=True),PadState(lx=10,ly=20,rx=200,ry=210),0);self.assertEqual((state.lx,state.ly,state.rx,state.ry),(200,210,10,255-20))
 def test_turbo_repeats_while_held(self):
  fast=profile(turbo=['cross','r2'],turbo_rate=10);held=PadState(buttons=CROSS|SQUARE,r2=255)
  seen=[pp.apply(fast,held,moment/100) for moment in range(0,20)]
  self.assertEqual({bool(state.buttons&CROSS) for state in seen},{True,False});self.assertTrue(all(state.buttons&SQUARE for state in seen))
  self.assertEqual(sum(1 for state in seen if state.buttons&CROSS),10,'on half the time');self.assertEqual({state.r2 for state in seen},{0,255})
  self.assertEqual(pp.apply(fast,NEUTRAL,.06),NEUTRAL)
 def test_one_hand(self):
  left=profile(one_hand='left')
  self.assertEqual(pp.apply(left,PadState(buttons=UP),0).buttons,UP,'the D-pad is itself without L1')
  state=pp.apply(left,PadState(buttons=L1|UP|LEFT,lx=0,ly=40),0);self.assertEqual((state.buttons,state.rx,state.ry,state.lx,state.ly),(TRIANGLE|SQUARE,0,40,128,128))
  state=pp.apply(profile(one_hand='right'),PadState(buttons=R1|CROSS,rx=255,ry=0),0);self.assertEqual((state.buttons,state.lx,state.ly,state.rx),(pp.BUTTONS['down'],255,0,128))
 def test_settings_are_cleaned_and_described(self):
  made=pp.clean(dict(remap=[['cross','cross'],['nope','l1'],['l1','r1']],turbo=['cross','options'],turbo_rate=7,one_hand='feet',swap_face=1))
  self.assertEqual((made['remap'],made['turbo'],made['turbo_rate'],made['one_hand'],made['swap_face']),([['l1','r1']],['cross'],10,'off',True))
  self.assertEqual(pp.describe(pp.clean({})),'As the controller is: nothing changed.')
  self.assertEqual(pp.describe(profile(remap=[['l1','r1']],turbo=['cross'],one_hand='left')),'L1 plays as R1; turbo on ✕ at 10 a second; one hand: the left, holding L1.')
  self.assertEqual(pp.describe(profile(swap_face=True)),'✕ and ○ swapped.')
 def test_each_game_keeps_its_own(self):
  folder=Path(tempfile.mkdtemp());self.addCleanup(shutil.rmtree,folder,True);path=folder/'controller.json'
  profiles=pp.PadProfiles(path);profiles.set('',swap_face=True);profiles.set('PPSA01',turbo=['cross'])
  again=pp.PadProfiles(path);self.assertTrue(again.get('PPSA02')['swap_face']);self.assertEqual(again.get('PPSA01')['turbo'],['cross']);self.assertTrue(again.get('PPSA01')['swap_face'],'a game starts from the one for every game')
  self.assertTrue(again.own('PPSA01'));again.forget('PPSA01');self.assertFalse(pp.PadProfiles(path).own('PPSA01'))

if __name__=='__main__':unittest.main()
