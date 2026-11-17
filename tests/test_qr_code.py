import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import phone_link,qr_code

# Made by an independent QR code generator for the same text and level; qr_code gave the same symbols, mask included, for every
# level and forced mask over versions 1 to 10 when it was written.
REFERENCE={('http://192.168.1.23:8090/#code=123456','M'):(841,'1fc44a7f820fa20dd6cc176ea67abb75f825d8287220ff5555fc03568017cd7f7c89c8728bb6ce0c221285a574a3facb93632a9b8fb71125105453cd7984dcb836ecd1cf132766c5a577239f700f678fff03ed720b3622175059fcba9c2d1dd55cd6a08f6b65fdd680c'),
 ('Hello','L'):(441,'1fcb7f82720dd6d76e94bb7455d820a0ff55fc03601dfec4e062195847ef2885e5d50009537f6b9e0bf61752e3ba6335d74560a0a5fd163')}

def read_format(rows):
 """The level and mask a symbol's format information gives, read back from beside the top-left finder."""
 bits=0;size=len(rows)
 places=[(8,i) for i in range(6)]+[(8,7),(8,8),(7,8)]+[(14-i,8) for i in range(9,15)]
 for i,(x,y) in enumerate(places):bits|=rows[y][x]<<i
 bits^=0x5412;level={1:'L',0:'M',3:'Q',2:'H'}[bits>>13];mask=bits>>10&7
 second=0
 for i in range(8):second|=rows[8][size-1-i]<<i
 for i in range(8,15):second|=rows[size-15+i][8]<<i
 return level,mask,second^0x5412==bits

class QrCodeTests(unittest.TestCase):
 def test_symbols_match_an_independent_generator(self):
  for (text,level),(length,expected) in REFERENCE.items():
   self.assertEqual(qr_code.as_text(qr_code.encode(text,level)),bin(int(expected,16))[2:].zfill(length),(text,level))
 def test_the_smallest_version_that_holds_the_text(self):
  self.assertEqual(len(qr_code.encode('a'*14,'M')),21);self.assertEqual(len(qr_code.encode('a'*15,'M')),25)
  self.assertEqual(len(qr_code.encode('a'*213,'M')),57)
  with self.assertRaises(ValueError):qr_code.encode('a'*214,'M')
 def test_finders_timing_and_format_are_where_a_camera_looks(self):
  for level in 'LMQH':
   rows=qr_code.encode('http://192.168.1.23:8090/',level,mask=5);size=len(rows)
   for x0,y0 in ((0,0),(size-7,0),(0,size-7)):
    self.assertEqual([rows[y0][x0+i] for i in range(7)],[1]*7);self.assertEqual([rows[y0+2][x0+i] for i in range(7)],[1,0,1,1,1,0,1])
   self.assertEqual([rows[6][x] for x in range(8,size-8)],[(x+1)%2 for x in range(8,size-8)])
   self.assertEqual(read_format(rows),(level,5,True));self.assertEqual(rows[size-8][8],1)
 def test_the_error_correction_checks_out(self):
  # Every block's data and check bytes, as a polynomial, vanish at the generator's roots.
  words=qr_code.codewords(b'http://192.168.1.23:8090/#code=123456',4,'M')
  self.assertEqual(len(words),100)
  blocks=qr_code.BLOCKS['M'][3];ecc=qr_code.ECC_PER_BLOCK['M'][3];per=100//blocks;self.assertEqual(blocks,2)
  for b in range(blocks):
   block=[words[i*blocks+b] for i in range(per-ecc)]+[words[(per-ecc)*blocks+i*blocks+b] for i in range(ecc)]
   root=1
   for _ in range(ecc):
    value=0
    for byte in block:value=qr_code.gf_multiply(value,root)^byte
    self.assertEqual(value,0);root=qr_code.gf_multiply(root,2)
 def test_the_phone_address_carries_the_pairing_code_after_the_hash(self):
  self.assertEqual(phone_link.scan_address('http://192.168.1.23:8090','123456'),'http://192.168.1.23:8090/#code=123456')
  self.assertEqual(phone_link.scan_address('http://192.168.1.23:8090',''),'http://192.168.1.23:8090/')
  self.assertEqual(phone_link.scan_address('http://192.168.1.23:8090','12ab'),'http://192.168.1.23:8090/')
  self.assertEqual(phone_link.scan_address('',''),'')
 def test_the_phone_page_pairs_from_the_scanned_code_and_clears_it(self):
  page=phone_link.PAGE.read_text(encoding='utf8')
  self.assertIn('location.hash.match',page);self.assertIn('history.replaceState',page);self.assertIn('$("code").value = scanned',page)

if __name__=='__main__':unittest.main()
