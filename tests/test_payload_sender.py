import os,socket,sys,tempfile,threading,unittest
from pathlib import Path
if os.environ.get('PLAYBRIDGE_DEPS'):sys.path.insert(0,os.environ['PLAYBRIDGE_DEPS'])
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
import payload_sender as p

def elf(machine=0x3E,width=2,order=1,body=b'payload'):
 return b'\x7fELF'+bytes((width,order,1))+bytes(9)+(2).to_bytes(2,'little')+machine.to_bytes(2,'little')+body

class FileTests(unittest.TestCase):
 def setUp(self):self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
 def write(self,data,name='test.elf'):
  path=Path(self.folder.name)/name;path.write_bytes(data);return path
 def test_a_ps5_elf_is_read_whole(self):
  data=elf();self.assertEqual(p.read_payload(self.write(data)),data)
 def test_anything_else_is_refused_with_a_reason(self):
  with self.assertRaisesRegex(p.PayloadError,'not an ELF'):p.read_payload(self.write(b'MZ'+bytes(64)))
  with self.assertRaisesRegex(p.PayloadError,'64-bit x86'):p.read_payload(self.write(elf(machine=0xB7)))
  with self.assertRaisesRegex(p.PayloadError,'64-bit x86'):p.read_payload(self.write(elf(width=1)))
  with self.assertRaisesRegex(p.PayloadError,'64-bit x86'):p.read_payload(self.write(b'\x7fELF'))
  with self.assertRaisesRegex(p.PayloadError,'cannot be read'):p.read_payload(Path(self.folder.name)/'missing.elf')
 def test_a_huge_file_is_refused_before_it_is_read(self):
  path=self.write(elf())
  with open(path,'r+b') as f:f.truncate(p.LIMIT+1)
  with self.assertRaisesRegex(p.PayloadError,'64 MB'):p.read_payload(path)
 def test_recent_files_keep_the_newest_first_and_each_once(self):
  recent=[]
  for name in ('a','b','c','b','d','e','f'):recent=p.remember(recent,name)
  self.assertEqual(recent,['f','e','d','b','c'])
 def test_sizes_read_naturally(self):
  self.assertEqual(p.size_label(300),'1 KB');self.assertEqual(p.size_label(150*1024),'150 KB');self.assertEqual(p.size_label(3*1024*1024),'3.0 MB')

class LoaderTests(unittest.TestCase):
 def test_the_loader_gets_every_byte_then_the_end(self):
  server=socket.create_server(('127.0.0.1',0));port=server.getsockname()[1];got=[]
  def accept():
   connection,_=server.accept();parts=[]
   with connection:
    while chunk:=connection.recv(65536):parts.append(chunk)
   got.append(b''.join(parts))
  thread=threading.Thread(target=accept);thread.start()
  data=elf(body=os.urandom(300000))
  try:p.send_payload('127.0.0.1',data,port=port)
  finally:thread.join(5);server.close()
  self.assertEqual(got,[data])
 def test_no_loader_says_to_load_one(self):
  server=socket.create_server(('127.0.0.1',0));port=server.getsockname()[1];server.close()
  with self.assertRaisesRegex(p.PayloadError,'Load the ELF loader'):p.send_payload('127.0.0.1',elf(),port=port)

if __name__=='__main__':unittest.main()
