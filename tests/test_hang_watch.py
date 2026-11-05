import sys,threading,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
from hang_watch import HangWatch,where

class HangWatchTests(unittest.TestCase):
 def watched(self,work):
  stop=threading.Event();result={}
  def thread():
   watch=HangWatch(threading.get_ident(),stop,threshold=.1,every=.03)
   result['before']=watch.beat();work();result['after']=watch.beat()
  runner=threading.Thread(target=thread);runner.start();runner.join(5);stop.set();return result
 def test_a_thread_that_stops_answering_is_found_where_it_stopped(self):
  def slow_resize():time.sleep(.5)
  result=self.watched(slow_resize)
  self.assertEqual(result['before'],'');self.assertIn('slow_resize',result['after']);self.assertIn('test_hang_watch.py',result['after'])
 def test_a_thread_that_keeps_answering_reports_nothing(self):
  self.assertEqual(self.watched(lambda:time.sleep(.02))['after'],'')
 def test_the_stack_reads_innermost_first(self):
  def inner():return where(sys._getframe())
  def outer():return inner()
  self.assertTrue(outer().startswith('test_hang_watch.py:'));self.assertLess(outer().index(' inner'),outer().index(' outer'))
if __name__=='__main__':unittest.main()
