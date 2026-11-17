"""QR codes for the addresses a phone opens, so it does not have to type them: byte mode (UTF-8), versions 1 to 10, any error
correction level. Made from the QR Code standard (ISO/IEC 18004); a phone's camera app reads them.

encode(text) gives the symbol as rows of 0 and 1 (1 is dark), without the light margin around it, which the drawing adds."""

# Per version 1-10: the error correction codewords in each block and the number of blocks, for levels L, M, Q, H.
ECC_PER_BLOCK={'L':(7,10,15,20,26,18,20,24,30,18),'M':(10,16,26,18,24,16,18,22,22,26),'Q':(13,22,18,26,18,24,18,22,20,24),'H':(17,28,22,16,22,28,26,26,24,28)}
BLOCKS={'L':(1,1,1,1,1,2,2,2,2,4),'M':(1,1,1,2,2,4,4,4,5,5),'Q':(1,1,2,2,4,4,6,6,8,8),'H':(1,1,2,4,4,4,5,6,8,8)}
# What the format information says for each level.
LEVEL_BITS={'L':1,'M':0,'Q':3,'H':2}
MAX_VERSION=10

def size_of(version):return version*4+17

# Where the alignment patterns' centres sit along each axis, and the codewords each version holds.
ALIGNMENT=((),(6,18),(6,22),(6,26),(6,30),(6,34),(6,22,38),(6,24,42),(6,26,46),(6,28,50))
TOTAL_CODEWORDS=(26,44,70,100,134,172,196,242,292,346)

def alignment_positions(version):return list(ALIGNMENT[version-1])
def raw_codewords(version):return TOTAL_CODEWORDS[version-1]

def data_codewords(version,level):return raw_codewords(version)-ECC_PER_BLOCK[level][version-1]*BLOCKS[level][version-1]

# Arithmetic in GF(256) with the QR code's polynomial, x^8 + x^4 + x^3 + x^2 + 1.
def gf_multiply(a,b):
 result=0
 for i in range(7,-1,-1):
  result=(result<<1)^((result>>7)*0x11D)
  result^=((b>>i)&1)*a
 return result&0xFF

def rs_divisor(degree):
 """The generator polynomial (x - 1)(x - 2)(x - 4)… of the given degree, its leading 1 left out."""
 coefficients=[0]*(degree-1)+[1];root=1
 for _ in range(degree):
  for j in range(degree):
   coefficients[j]=gf_multiply(coefficients[j],root)
   if j+1<degree:coefficients[j]^=coefficients[j+1]
  root=gf_multiply(root,2)
 return coefficients

def rs_remainder(data,divisor):
 result=[0]*len(divisor)
 for byte in data:
  factor=byte^result.pop(0);result.append(0)
  for i,coefficient in enumerate(divisor):result[i]^=gf_multiply(coefficient,factor)
 return result

def bch(value,generator,bits):
 """value followed by its BCH check bits."""
 remainder=value
 for _ in range(bits):remainder=(remainder<<1)^((remainder>>(bits-1))*generator)
 return value<<bits|remainder&((1<<bits)-1)

def codewords(data,version,level):
 """The data in byte mode, padded to the version's room, split into blocks, each with its error correction, and interleaved."""
 count_bits=8 if version<10 else 16
 bits=[0,1,0,0]+[(len(data)>>i)&1 for i in range(count_bits-1,-1,-1)]
 for byte in data:bits+=[(byte>>i)&1 for i in range(7,-1,-1)]
 room=data_codewords(version,level)*8
 bits+=[0]*min(4,room-len(bits));bits+=[0]*(-len(bits)%8)
 words=[int(''.join(map(str,bits[i:i+8])),2) for i in range(0,len(bits),8)]
 pad=0
 while len(words)<room//8:words.append((0xEC,0x11)[pad%2]);pad+=1
 blocks=BLOCKS[level][version-1];ecc=ECC_PER_BLOCK[level][version-1];raw=raw_codewords(version)
 short=blocks-raw%blocks;short_length=raw//blocks;divisor=rs_divisor(ecc)
 split=[];at=0
 for i in range(blocks):
  length=short_length-ecc+(0 if i<short else 1)
  part=words[at:at+length];at+=length
  split.append((part,rs_remainder(part,divisor)))
 out=[]
 for i in range(short_length-ecc+1):
  for part,_ in split:
   if i<len(part):out.append(part[i])
 for i in range(ecc):
  for _,check in split:out.append(check[i])
 return out

def mask_hit(mask,x,y):
 return (lambda:(x+y)%2==0,lambda:y%2==0,lambda:x%3==0,lambda:(x+y)%3==0,lambda:(x//3+y//2)%2==0,
  lambda:x*y%2+x*y%3==0,lambda:(x*y%2+x*y%3)%2==0,lambda:((x+y)%2+x*y%3)%2==0)[mask]()

class Symbol:
 def __init__(self,version):
  self.version=version;self.size=size_of(version)
  self.dark=[[0]*self.size for _ in range(self.size)];self.fixed=[[False]*self.size for _ in range(self.size)]
 def put(self,x,y,dark):self.dark[y][x]=int(bool(dark));self.fixed[y][x]=True
 def patterns(self):
  size=self.size
  for i in range(size):self.put(6,i,i%2==0);self.put(i,6,i%2==0)
  for cx,cy in ((3,3),(size-4,3),(3,size-4)):
   for dy in range(-4,5):
    for dx in range(-4,5):
     x,y=cx+dx,cy+dy
     if 0<=x<size and 0<=y<size:self.put(x,y,max(abs(dx),abs(dy)) not in (2,4))
  places=alignment_positions(self.version);last=len(places)-1
  for i,cx in enumerate(places):
   for j,cy in enumerate(places):
    if (i,j) in ((0,0),(0,last),(last,0)):continue
    for dy in range(-2,3):
     for dx in range(-2,3):self.put(cx+dx,cy+dy,max(abs(dx),abs(dy))!=1)
  self.format_bits('M',0)
  if self.version>=7:
   bits=bch(self.version,0x1F25,12)
   for i in range(18):
    a,b=size-11+i%3,i//3;self.put(a,b,bits>>i&1);self.put(b,a,bits>>i&1)
 def format_bits(self,level,mask):
  bits=bch(LEVEL_BITS[level]<<3|mask,0x537,10)^0x5412;size=self.size
  for i in range(6):self.put(8,i,bits>>i&1)
  self.put(8,7,bits>>6&1);self.put(8,8,bits>>7&1);self.put(7,8,bits>>8&1)
  for i in range(9,15):self.put(14-i,8,bits>>i&1)
  for i in range(8):self.put(size-1-i,8,bits>>i&1)
  for i in range(8,15):self.put(8,size-15+i,bits>>i&1)
  self.put(8,size-8,1)
 def place(self,words):
  size=self.size;at=0;total=len(words)*8;right=size-1
  while right>=1:
   if right==6:right=5
   for vertical in range(size):
    for j in range(2):
     x=right-j;y=size-1-vertical if (right+1)&2==0 else vertical
     if not self.fixed[y][x] and at<total:
      self.dark[y][x]=words[at>>3]>>(7-(at&7))&1;at+=1
   right-=2
 def apply(self,mask):
  for y in range(self.size):
   for x in range(self.size):
    if not self.fixed[y][x] and mask_hit(mask,x,y):self.dark[y][x]^=1

def penalty(rows):
 """The standard's score for how hard a symbol is to read; the mask with the lowest wins."""
 size=len(rows);score=0
 lines=[list(row) for row in rows]+[[rows[y][x] for y in range(size)] for x in range(size)]
 for line in lines:
  runs=[]
  for value in line:
   if runs and runs[-1][0]==value:runs[-1][1]+=1
   else:runs.append([value,1])
  for value,length in runs:
   if length>=5:score+=3+length-5
  # Finder-like stretches, dark 1:1:3:1:1, with four modules of light on one side. Beyond the edge counts as light.
  if runs[0][0]==0:runs[0][1]+=size
  else:runs.insert(0,[0,size])
  if runs[-1][0]==0:runs[-1][1]+=size
  else:runs.append([0,size])
  for i in range(1,len(runs)-5):
   part=runs[i:i+5]
   if part[0][0]!=1:continue
   n=part[0][1]
   if [length for _,length in part]!=[n,n,3*n,n,n]:continue
   before,after=runs[i-1][1],runs[i+5][1]
   score+=40*((before>=4*n and after>=n)+(after>=4*n and before>=n))
 for y in range(size-1):
  for x in range(size-1):
   if rows[y][x]==rows[y][x+1]==rows[y+1][x]==rows[y+1][x+1]:score+=3
 dark=sum(map(sum,rows));total=size*size
 score+=((abs(dark*20-total*10)+total-1)//total-1)*10
 return score

def encode(text,level='M',version=None,mask=None):
 """The QR code for text as rows of 0 and 1. The smallest version that holds it, and the most readable mask, unless given."""
 data=text.encode('utf8') if isinstance(text,str) else bytes(text)
 if version is None:
  version=next((v for v in range(1,MAX_VERSION+1) if 4+(8 if v<10 else 16)+8*len(data)<=data_codewords(v,level)*8),None)
  if version is None:raise ValueError(f'too long for a QR code here ({len(data)} bytes)')
 words=codewords(data,version,level);best=None
 for candidate in (range(8) if mask is None else (mask,)):
  symbol=Symbol(version);symbol.patterns();symbol.place(words);symbol.apply(candidate);symbol.format_bits(level,candidate)
  score=penalty(symbol.dark) if mask is None else 0
  if best is None or score<best[0]:best=(score,symbol.dark)
 return best[1]

def as_text(rows):
 """One string of 0 and 1, row after row, for the window to draw."""
 return ''.join(''.join(map(str,row)) for row in rows)
