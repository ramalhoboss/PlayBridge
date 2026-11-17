import re,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'app'))
import windows_look

class WindowsLookTests(unittest.TestCase):
 def test_windows_answers_are_plain_yes_or_no(self):
  self.assertIsInstance(windows_look.animations(),bool);self.assertIsInstance(windows_look.high_contrast(),bool)
 def test_every_fixed_text_size_follows_text_size(self):
  # A number written straight into font.pixelSize would stay small when Appearance › Text size is Larger or Largest.
  for path in (ROOT/'app'/'qml').glob('*.qml'):
   if path.name=='Theme.qml':continue
   for number,line in enumerate(path.read_text(encoding='utf8').splitlines(),1):
    self.assertIsNone(re.search(r'font\.pixelSize: \d+\s*(;|}|$)',line),f'{path.name}:{number}')

if __name__=='__main__':unittest.main()
