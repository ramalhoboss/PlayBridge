/* The secured link between PlayBridge on a PC and its payloads (app/secure_link.py is the PC side). No console calls and no C library
   here, so the PC tests build this file as it is and check it against the published test vectors and against Windows' own AES-GCM.

   The PC that sends a payload writes its pairing key into the payload's slot (SECURE_SLOT_*) before sending it. A payload whose slot
   holds no key works as before, for a PlayBridge.elf loaded by hand. One that holds a key takes no connection that cannot prove it:
     payload -> PC  'PBK1', version, channel, 2 zero bytes, a fresh 16-byte number of its own (Ns)                  24 bytes
     PC -> payload  'PBK2', a fresh 16-byte number of the PC's (Nc), HMAC-SHA256(key, "PlayBridge 1 client" ...)    52 bytes
     payload -> PC  'PBK3', HMAC-SHA256(key, "PlayBridge 1 server" ...)                                              36 bytes
   Each HMAC covers the label with its zero byte, the channel and both numbers. The payload answers only a PC that proved the key, and
   the PC goes on only with a payload that did. Each direction then has its own AES-256-GCM key, HMAC-SHA256(key, "PlayBridge 1 c2s" or
   "s2c" ...), fresh for every connection, and every record is its length (4 bytes, little-endian, authenticated), the sealed bytes and
   the 16-byte tag, with a nonce of 4 zero bytes and the record's number (8 bytes, little-endian).

   The controller companion's datagrams (UDP) cannot keep a conversation, so each sender says hello first:
     PC -> companion 'PBK4', Nc                                                                                     20 bytes
     companion -> PC 'PBK5', Nc, Ns, HMAC-SHA256(key, "PlayBridge 1 server" ...)                                     68 bytes
   and every datagram after that is 'PBX1', its number (8 bytes), the sealed bytes and the tag, the first 12 bytes authenticated. A number
   that is not higher than the last one taken is a datagram seen before, and is dropped. A new hello makes new keys, so datagrams of an
   earlier conversation never open again.
   Play away from home sends the picture and sound as such datagrams too (fec-rules.h), with keys made as for a connection on channel
   SECURE_VIDEO_UDP from the video connection's two numbers, and the PC's reports come back the same way.

   AES and GHASH use the processor's AES-NI and carry-less multiply, which every PS5 and every PC this runs on has. */
#ifndef SECURE_RULES_H
#define SECURE_RULES_H
#include <stddef.h>
#include <stdint.h>
/* The feature headers themselves: on Windows and on the PS5, immintrin.h leaves out every part whose -m flag was not given. */
#include <emmintrin.h>
#include <tmmintrin.h>
#include <wmmintrin.h>
/* The video payload uses the connection parts, the controller companion the datagram ones. */
#define SECURE_PART __attribute__((unused))

#define SECURE_SLOT_SIZE 64
#define SECURE_KEY_AT 16
#define SECURE_FLAGS_AT 48
/* Flags the PC writes beside the key. Away: the payload keeps waiting for this PC (play away from home). */
#define SECURE_FLAG_AWAY 1u
/* Trace: every log line also goes to the payload's standard output, which the ELF loader hands back over the connection that sent the
   payload, so a test on the PC reads each step as it happens, the last one before a payload stops too. Only a test tool sets it. */
#define SECURE_FLAG_TRACE 2u
#define SECURE_RECORD_MAX 65536u
#define SECURE_TAG 16
#define SECURE_RECORD_EXTRA (4+SECURE_TAG)
#define SECURE_HELLO_SIZE 24
#define SECURE_ANSWER_SIZE 52
#define SECURE_PROOF_SIZE 36
#define SECURE_PAD_HELLO_SIZE 20
#define SECURE_PAD_REPLY_SIZE 68
#define SECURE_DATAGRAM_EXTRA (12+SECURE_TAG)
/* SECURE_VIDEO_UDP keys the picture and sound over UDP (fec-rules.h), from the numbers of the video connection's handshake. */
enum{SECURE_VIDEO=1,SECURE_CONTROL=2,SECURE_MIC=3,SECURE_PAD=4,SECURE_VIDEO_UDP=5};

/* SHA-256 (FIPS 180-4), for the HMACs of the handshake only. */
struct secure_sha{uint32_t h[8];uint64_t n;unsigned char b[64];};
static const uint32_t secure_sha_k[64]={
 0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,
 0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
 0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,
 0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
 0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,
 0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
static uint32_t secure_ror(uint32_t x,int n){return (x>>n)|(x<<(32-n));}
static void secure_sha_block(uint32_t*h,const unsigned char*p){
 uint32_t w[64];
 for(int i=0;i<16;i++)w[i]=(uint32_t)p[4*i]<<24|(uint32_t)p[4*i+1]<<16|(uint32_t)p[4*i+2]<<8|(uint32_t)p[4*i+3];
 for(int i=16;i<64;i++){
  uint32_t s0=secure_ror(w[i-15],7)^secure_ror(w[i-15],18)^(w[i-15]>>3),s1=secure_ror(w[i-2],17)^secure_ror(w[i-2],19)^(w[i-2]>>10);
  w[i]=w[i-16]+s0+w[i-7]+s1;
 }
 uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],k=h[7];
 for(int i=0;i<64;i++){
  uint32_t t1=k+(secure_ror(e,6)^secure_ror(e,11)^secure_ror(e,25))+((e&f)^(~e&g))+secure_sha_k[i]+w[i];
  uint32_t t2=(secure_ror(a,2)^secure_ror(a,13)^secure_ror(a,22))+((a&b)^(a&c)^(b&c));
  k=g;g=f;f=e;e=d+t1;d=c;c=b;b=a;a=t1+t2;
 }
 h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=k;
}
static void secure_sha_init(struct secure_sha*s){
 static const uint32_t start[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
 for(int i=0;i<8;i++)s->h[i]=start[i];
 s->n=0;
}
static void secure_sha_add(struct secure_sha*s,const void*data,size_t n){
 const unsigned char*p=data;
 while(n--){s->b[s->n%64]=*p++;s->n++;if(s->n%64==0)secure_sha_block(s->h,s->b);}
}
static void secure_sha_end(struct secure_sha*s,unsigned char out[32]){
 uint64_t bits=s->n*8;unsigned char one=0x80,zero=0,length[8];
 secure_sha_add(s,&one,1);
 while(s->n%64!=56)secure_sha_add(s,&zero,1);
 for(int i=0;i<8;i++)length[i]=(unsigned char)(bits>>(56-8*i));
 secure_sha_add(s,length,8);
 for(int i=0;i<8;i++){out[4*i]=(unsigned char)(s->h[i]>>24);out[4*i+1]=(unsigned char)(s->h[i]>>16);out[4*i+2]=(unsigned char)(s->h[i]>>8);out[4*i+3]=(unsigned char)s->h[i];}
}
/* HMAC-SHA256 (RFC 2104) with a key of at most 64 bytes; PlayBridge's are 32. */
struct secure_hmac{struct secure_sha inner,outer;};
static void secure_hmac_init(struct secure_hmac*m,const unsigned char*key,size_t n){
 unsigned char pad[64];
 for(size_t i=0;i<64;i++)pad[i]=(unsigned char)((i<n?key[i]:0)^0x36);
 secure_sha_init(&m->inner);secure_sha_add(&m->inner,pad,64);
 for(size_t i=0;i<64;i++)pad[i]^=0x36^0x5c;
 secure_sha_init(&m->outer);secure_sha_add(&m->outer,pad,64);
}
static void secure_hmac_end(struct secure_hmac*m,unsigned char out[32]){
 unsigned char inner[32];secure_sha_end(&m->inner,inner);secure_sha_add(&m->outer,inner,32);secure_sha_end(&m->outer,out);
}
/* HMAC(key, label with its zero byte, channel, Ns, Nc). */
static void secure_derive(const unsigned char key[32],const char*label,int channel,const unsigned char ns[16],const unsigned char nc[16],unsigned char out[32]){
 struct secure_hmac m;secure_hmac_init(&m,key,32);
 size_t n=0;while(label[n])n++;
 unsigned char c=(unsigned char)channel;
 secure_sha_add(&m.inner,label,n+1);secure_sha_add(&m.inner,&c,1);secure_sha_add(&m.inner,ns,16);secure_sha_add(&m.inner,nc,16);
 secure_hmac_end(&m,out);
}
/* Equal without saying where they differ: 1 when the n bytes match. */
static int secure_same(const unsigned char*a,const unsigned char*b,size_t n){
 unsigned char d=0;for(size_t i=0;i<n;i++)d|=(unsigned char)(a[i]^b[i]);
 return d==0;
}

/* AES-256 and GCM (NIST SP 800-38D) with 12-byte nonces. */
#define SECURE_SIMD __attribute__((target("aes,pclmul,sse2,ssse3")))
struct secure_gcm{__m128i rk[15];__m128i h;};
/* k, then the word before it XORed in, three times over: each word becomes the XOR of itself and every word below it. */
SECURE_SIMD static __m128i secure_spread(__m128i k){
 __m128i t=_mm_slli_si128(k,4);k=_mm_xor_si128(k,t);t=_mm_slli_si128(t,4);k=_mm_xor_si128(k,t);t=_mm_slli_si128(t,4);return _mm_xor_si128(k,t);
}
#define SECURE_EVEN_KEY(r,i,rcon) r[i]=_mm_xor_si128(secure_spread(r[i-2]),_mm_shuffle_epi32(_mm_aeskeygenassist_si128(r[i-1],rcon),0xff))
#define SECURE_ODD_KEY(r,i) r[i]=_mm_xor_si128(secure_spread(r[i-2]),_mm_shuffle_epi32(_mm_aeskeygenassist_si128(r[i-1],0),0xaa))
SECURE_SIMD static __m128i secure_aes(const struct secure_gcm*g,__m128i x){
 x=_mm_xor_si128(x,g->rk[0]);
 for(int i=1;i<14;i++)x=_mm_aesenc_si128(x,g->rk[i]);
 return _mm_aesenclast_si128(x,g->rk[14]);
}
SECURE_SIMD static __m128i secure_swap(__m128i x){return _mm_shuffle_epi8(x,_mm_set_epi8(0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15));}
/* a*b in GF(2^128) as GCM defines it, both byte-swapped (Gueron and Kounavis, Intel's carry-less multiplication guide, algorithm 5). */
SECURE_SIMD static __m128i secure_gfmul(__m128i a,__m128i b){
 __m128i lo=_mm_clmulepi64_si128(a,b,0x00),mid=_mm_xor_si128(_mm_clmulepi64_si128(a,b,0x10),_mm_clmulepi64_si128(a,b,0x01)),hi=_mm_clmulepi64_si128(a,b,0x11);
 lo=_mm_xor_si128(lo,_mm_slli_si128(mid,8));hi=_mm_xor_si128(hi,_mm_srli_si128(mid,8));
 /* The 256-bit product one bit to the left. */
 __m128i lo_carry=_mm_srli_epi32(lo,31),hi_carry=_mm_srli_epi32(hi,31),across=_mm_srli_si128(lo_carry,12);
 lo=_mm_or_si128(_mm_slli_epi32(lo,1),_mm_slli_si128(lo_carry,4));
 hi=_mm_or_si128(_mm_or_si128(_mm_slli_epi32(hi,1),_mm_slli_si128(hi_carry,4)),across);
 /* Reduced by x^128 + x^7 + x^2 + x + 1. */
 __m128i a1=_mm_xor_si128(_mm_xor_si128(_mm_slli_epi32(lo,31),_mm_slli_epi32(lo,30)),_mm_slli_epi32(lo,25));
 __m128i a2=_mm_srli_si128(a1,4);
 lo=_mm_xor_si128(lo,_mm_slli_si128(a1,12));
 __m128i b1=_mm_xor_si128(_mm_xor_si128(_mm_srli_epi32(lo,1),_mm_srli_epi32(lo,2)),_mm_srli_epi32(lo,7));
 b1=_mm_xor_si128(b1,a2);lo=_mm_xor_si128(lo,b1);
 return _mm_xor_si128(hi,lo);
}
SECURE_SIMD static void secure_gcm_init(struct secure_gcm*g,const unsigned char key[32]){
 __m128i*r=g->rk;
 r[0]=_mm_loadu_si128((const __m128i*)key);r[1]=_mm_loadu_si128((const __m128i*)(key+16));
 SECURE_EVEN_KEY(r,2,0x01);SECURE_ODD_KEY(r,3);SECURE_EVEN_KEY(r,4,0x02);SECURE_ODD_KEY(r,5);SECURE_EVEN_KEY(r,6,0x04);SECURE_ODD_KEY(r,7);
 SECURE_EVEN_KEY(r,8,0x08);SECURE_ODD_KEY(r,9);SECURE_EVEN_KEY(r,10,0x10);SECURE_ODD_KEY(r,11);SECURE_EVEN_KEY(r,12,0x20);SECURE_ODD_KEY(r,13);
 SECURE_EVEN_KEY(r,14,0x40);
 g->h=secure_swap(secure_aes(g,_mm_setzero_si128()));
}
SECURE_SIMD static __m128i secure_counter(const unsigned char iv[12],uint32_t c){
 unsigned char b[16];
 for(int i=0;i<12;i++)b[i]=iv[i];
 b[12]=(unsigned char)(c>>24);b[13]=(unsigned char)(c>>16);b[14]=(unsigned char)(c>>8);b[15]=(unsigned char)c;
 return _mm_loadu_si128((const __m128i*)b);
}
/* GHASH over n bytes, the last block padded with zeros. */
SECURE_SIMD static __m128i secure_ghash(const struct secure_gcm*g,__m128i x,const unsigned char*p,size_t n){
 for(;n>=16;p+=16,n-=16)x=secure_gfmul(_mm_xor_si128(x,secure_swap(_mm_loadu_si128((const __m128i*)p))),g->h);
 if(n){
  unsigned char b[16]={0};for(size_t i=0;i<n;i++)b[i]=p[i];
  x=secure_gfmul(_mm_xor_si128(x,secure_swap(_mm_loadu_si128((const __m128i*)b))),g->h);
 }
 return x;
}
/* The keystream from counter 2 on, XORed into n bytes; in and out may be the same place. */
SECURE_SIMD static void secure_ctr(const struct secure_gcm*g,const unsigned char iv[12],const unsigned char*in,size_t n,unsigned char*out){
 uint32_t c=2;
 for(;n>=16;in+=16,out+=16,n-=16)_mm_storeu_si128((__m128i*)out,_mm_xor_si128(_mm_loadu_si128((const __m128i*)in),secure_aes(g,secure_counter(iv,c++))));
 if(n){
  unsigned char k[16];_mm_storeu_si128((__m128i*)k,secure_aes(g,secure_counter(iv,c)));
  for(size_t i=0;i<n;i++)out[i]=in[i]^k[i];
 }
}
SECURE_SIMD static void secure_tag(const struct secure_gcm*g,const unsigned char iv[12],const unsigned char*aad,size_t an,const unsigned char*ct,size_t n,unsigned char tag[16]){
 __m128i x=secure_ghash(g,_mm_setzero_si128(),aad,an);x=secure_ghash(g,x,ct,n);
 unsigned char lengths[16];uint64_t ab=(uint64_t)an*8,cb=(uint64_t)n*8;
 for(int i=0;i<8;i++){lengths[i]=(unsigned char)(ab>>(56-8*i));lengths[8+i]=(unsigned char)(cb>>(56-8*i));}
 x=secure_ghash(g,x,lengths,16);
 _mm_storeu_si128((__m128i*)tag,_mm_xor_si128(secure_swap(x),secure_aes(g,secure_counter(iv,1))));
}
static void secure_gcm_seal(const struct secure_gcm*g,const unsigned char iv[12],const unsigned char*aad,size_t an,const unsigned char*in,size_t n,unsigned char*out,unsigned char tag[16]){
 secure_ctr(g,iv,in,n,out);secure_tag(g,iv,aad,an,out,n,tag);
}
/* 1 and the plain bytes in out when the tag is right; 0 and out untouched otherwise. */
static int secure_gcm_open(const struct secure_gcm*g,const unsigned char iv[12],const unsigned char*aad,size_t an,const unsigned char*in,size_t n,const unsigned char tag[16],unsigned char*out){
 unsigned char want[16];secure_tag(g,iv,aad,an,in,n,want);
 if(!secure_same(want,tag,16))return 0;
 secure_ctr(g,iv,in,n,out);return 1;
}

/* One direction of a connection: its key and the number of its next record (sending) or of the lowest it still takes (receiving). */
struct secure_dir{struct secure_gcm key;uint64_t count;};
static void secure_nonce(unsigned char iv[12],uint64_t count){
 for(int i=0;i<4;i++)iv[i]=0;
 for(int i=0;i<8;i++)iv[4+i]=(unsigned char)(count>>(8*i));
}
static void secure_dir_init(struct secure_dir*d,const unsigned char key[32]){secure_gcm_init(&d->key,key);d->count=0;}
/* One record of n bytes (1 to SECURE_RECORD_MAX) into out, which holds n+SECURE_RECORD_EXTRA; returns its size. */
SECURE_PART static size_t secure_seal_record(struct secure_dir*d,const unsigned char*in,uint32_t n,unsigned char*out){
 unsigned char iv[12];secure_nonce(iv,d->count++);
 out[0]=(unsigned char)n;out[1]=(unsigned char)(n>>8);out[2]=(unsigned char)(n>>16);out[3]=(unsigned char)(n>>24);
 secure_gcm_seal(&d->key,iv,out,4,in,n,out+4,out+4+n);
 return n+SECURE_RECORD_EXTRA;
}
/* The length a record's first 4 bytes give, or 0 when it is not one this side takes. */
SECURE_PART static uint32_t secure_record_length(const unsigned char head[4]){
 uint32_t n=(uint32_t)head[0]|(uint32_t)head[1]<<8|(uint32_t)head[2]<<16|(uint32_t)head[3]<<24;
 return n&&n<=SECURE_RECORD_MAX?n:0;
}
/* A whole record (its length, n sealed bytes and the tag) opened in place: 1 and the plain bytes at rec+4, or 0. */
SECURE_PART static int secure_open_record(struct secure_dir*d,unsigned char*rec,uint32_t n){
 unsigned char iv[12];secure_nonce(iv,d->count);
 if(!secure_gcm_open(&d->key,iv,rec,4,rec+4,n,rec+4+n,rec+4))return 0;
 d->count++;return 1;
}

/* The handshake (see the top of this file). */
SECURE_PART static void secure_hello(unsigned char out[SECURE_HELLO_SIZE],int channel,const unsigned char ns[16]){
 out[0]='P';out[1]='B';out[2]='K';out[3]='1';out[4]=1;out[5]=(unsigned char)channel;out[6]=out[7]=0;
 for(int i=0;i<16;i++)out[8+i]=ns[i];
}
static void secure_keys(const unsigned char key[32],int channel,const unsigned char ns[16],const unsigned char nc[16],struct secure_dir*from_pc,struct secure_dir*to_pc){
 unsigned char k[32];
 secure_derive(key,"PlayBridge 1 c2s",channel,ns,nc,k);secure_dir_init(from_pc,k);
 secure_derive(key,"PlayBridge 1 s2c",channel,ns,nc,k);secure_dir_init(to_pc,k);
 for(int i=0;i<32;i++)k[i]=0;
}
/* The PC's answer to a hello: 1 when it proved the key, with this side's proof in proof_out and both directions' keys set. */
SECURE_PART static int secure_check_answer(const unsigned char key[32],int channel,const unsigned char ns[16],const unsigned char in[SECURE_ANSWER_SIZE],
 struct secure_dir*from_pc,struct secure_dir*to_pc,unsigned char proof_out[SECURE_PROOF_SIZE]){
 if(in[0]!='P'||in[1]!='B'||in[2]!='K'||in[3]!='2')return 0;
 unsigned char want[32];secure_derive(key,"PlayBridge 1 client",channel,ns,in+4,want);
 if(!secure_same(want,in+20,32))return 0;
 proof_out[0]='P';proof_out[1]='B';proof_out[2]='K';proof_out[3]='3';
 secure_derive(key,"PlayBridge 1 server",channel,ns,in+4,proof_out+4);
 secure_keys(key,channel,ns,in+4,from_pc,to_pc);
 return 1;
}
/* A sender's hello to the controller companion: 1 with the reply to send and the keys set, 0 when it is not one. */
SECURE_PART static int secure_pad_hello(const unsigned char key[32],const unsigned char*in,size_t n,const unsigned char ns[16],unsigned char reply[SECURE_PAD_REPLY_SIZE],
 struct secure_dir*from_pc,struct secure_dir*to_pc){
 if(n!=SECURE_PAD_HELLO_SIZE||in[0]!='P'||in[1]!='B'||in[2]!='K'||in[3]!='4')return 0;
 reply[0]='P';reply[1]='B';reply[2]='K';reply[3]='5';
 for(int i=0;i<16;i++){reply[4+i]=in[4+i];reply[20+i]=ns[i];}
 secure_derive(key,"PlayBridge 1 server",SECURE_PAD,ns,in+4,reply+36);
 secure_keys(key,SECURE_PAD,ns,in+4,from_pc,to_pc);
 return 1;
}
SECURE_PART static int secure_is_pad_hello(const unsigned char*w,size_t n){return n==SECURE_PAD_HELLO_SIZE&&w[0]=='P'&&w[1]=='B'&&w[2]=='K'&&w[3]=='4';}
/* A datagram of n bytes sealed into out (n+SECURE_DATAGRAM_EXTRA); returns its size. */
SECURE_PART static size_t secure_seal_datagram(struct secure_dir*d,const unsigned char*in,size_t n,unsigned char*out){
 uint64_t count=d->count++;unsigned char iv[12];secure_nonce(iv,count);
 out[0]='P';out[1]='B';out[2]='X';out[3]='1';
 for(int i=0;i<8;i++)out[4+i]=(unsigned char)(count>>(8*i));
 secure_gcm_seal(&d->key,iv,out,12,in,n,out+12,out+12+n);
 return n+SECURE_DATAGRAM_EXTRA;
}
/* A sealed datagram opened in place: its plain size, with the bytes at w+12, or -1 when it is not one, does not open or was seen. */
SECURE_PART static long secure_open_datagram(struct secure_dir*d,unsigned char*w,size_t n){
 if(n<SECURE_DATAGRAM_EXTRA||w[0]!='P'||w[1]!='B'||w[2]!='X'||w[3]!='1')return -1;
 uint64_t count=0;for(int i=0;i<8;i++)count|=(uint64_t)w[4+i]<<(8*i);
 if(count<d->count)return -1;
 size_t m=n-SECURE_DATAGRAM_EXTRA;unsigned char iv[12];secure_nonce(iv,count);
 if(!secure_gcm_open(&d->key,iv,w,12,w+12,m,w+12+m,w+12))return -1;
 d->count=count+1;return (long)m;
}
/* The key and flags the PC wrote into a payload's slot: 1 when there is a key. */
SECURE_PART static int secure_key_of(const volatile unsigned char*slot,unsigned char key[32],uint32_t*flags){
 unsigned char any=0;uint32_t f=0;
 for(int i=0;i<32;i++){key[i]=slot[SECURE_KEY_AT+i];any|=key[i];}
 for(int i=0;i<4;i++)f|=(uint32_t)slot[SECURE_FLAGS_AT+i]<<(8*i);
 *flags=f;return any!=0;
}
#endif
