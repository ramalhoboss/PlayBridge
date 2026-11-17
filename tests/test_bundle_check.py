import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import bundle_check

COMPONENTS=ROOT/'third-party-licenses'/'components.json'
SITE=r'C:\Python\Lib\site-packages'

class BundleCheckTests(unittest.TestCase):
 def test_package_names_from_bundled_paths(self):
  cases={SITE+r'\PIL\Image.py':'pillow',SITE+r'\numpy.libs\libscipy.dll':'numpy',SITE+r'\av-19.0.2.dist-info\RECORD':'av',
   SITE+r'\_cffi_backend.cp312-win_amd64.pyd':'cffi',SITE+r'\typing_extensions.py':'typing_extensions',
   SITE+r'\shiboken6\shiboken6.abi3.dll':'pyside6',r'C:\Python\Lib\json\__init__.py':None,r'C:\Python\DLLs\_ssl.pyd':None}
  for path,name in cases.items():self.assertEqual(bundle_check.package_of(path),name,path)
 def test_only_packages_without_a_notice_are_named(self):
  entries=[('PIL.Image',SITE+r'\PIL\Image.py','PYMODULE'),('json',r'C:\Python\Lib\json\__init__.py','PYMODULE'),
   ('packaging.version',SITE+r'\packaging\version.py','PYMODULE'),('cryptography',SITE+r'\cryptography\__init__.py','PYMODULE'),
   ('charset_normalizer',SITE+r'\charset_normalizer\api.py','PYMODULE')]
  self.assertEqual(bundle_check.unlisted(entries,COMPONENTS),['charset_normalizer','cryptography'])
 def test_every_listed_component_has_its_licence_texts(self):
  import json
  for item in json.loads(COMPONENTS.read_text(encoding='utf8')):
   for name in item['licenses']:self.assertTrue((COMPONENTS.parent/item['component']/name).is_file(),(item['component'],name))

if __name__=='__main__':unittest.main()
