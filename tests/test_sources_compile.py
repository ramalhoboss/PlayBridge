"""Every module of the app compiles, including the ones no other test imports (the Qt shell needs a window to run)."""
import py_compile,tempfile,unittest
from pathlib import Path

APP=Path(__file__).resolve().parents[1]/'app'

class CompileTests(unittest.TestCase):
 def test_every_app_module_compiles(self):
  with tempfile.TemporaryDirectory() as folder:
   for source in sorted(APP.glob('*.py')):
    with self.subTest(module=source.name):py_compile.compile(str(source),cfile=str(Path(folder)/(source.stem+'.pyc')),doraise=True)

if __name__=='__main__':unittest.main()
