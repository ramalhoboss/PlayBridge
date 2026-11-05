"""Connecting to the payload's capture port after the upload."""
import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import playbridge as core

class Clock:
 def __init__(self):self.now=0.0
 def __call__(self):return self.now

class CaptureConnectTests(unittest.TestCase):
 def test_short_tries_go_on_until_the_payload_listens(self):
  sock=object();answers=[OSError(),OSError(),sock];calls=[];waits=[]
  def connect(address,timeout):
   calls.append((address,timeout));answer=answers.pop(0)
   if isinstance(answer,Exception):raise answer
   return answer
  with patch.object(core.socket,'create_connection',side_effect=connect):
   got=core.connect_capture('ps5',lambda seconds:waits.append(seconds) or False)
  self.assertIs(got,sock);self.assertEqual(calls,[(('ps5',9076),.5)]*3);self.assertEqual(waits,[.1,.1])
 def test_the_wait_is_counted_in_seconds_not_tries(self):
  # A PS5 that gives no answer at all: each try runs out its half second.
  clock=Clock();tries=[]
  def connect(address,timeout):tries.append(clock.now);clock.now+=timeout;raise OSError()
  def wait(seconds):clock.now+=seconds;return False
  with patch.object(core.socket,'create_connection',side_effect=connect):self.assertIsNone(core.connect_capture('ps5',wait,clock=clock))
  self.assertEqual(len(tries),17);self.assertGreaterEqual(clock.now,10);self.assertLess(clock.now,10.7)
 def test_it_stops_when_told_to(self):
  calls=[]
  def connect(address,timeout):calls.append(address);raise OSError()
  with patch.object(core.socket,'create_connection',side_effect=connect):self.assertIsNone(core.connect_capture('ps5',lambda seconds:True))
  self.assertEqual(len(calls),1)

if __name__=='__main__':unittest.main()
