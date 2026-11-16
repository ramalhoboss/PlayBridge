/* Error correction for the picture and sound over UDP, when the PC plays away from home and a lost datagram is never sent again.

   Each record (one 32-byte PSAV header and its packet, as the TCP stream carries them) goes out in fragments of FEC_FRAGMENT bytes.
   Every FEC_BLOCK fragments of a record form a block, and each block gets parity fragments: a systematic Reed-Solomon code over
   GF(256) (polynomial 0x11d) with a Cauchy matrix, so the PC rebuilds a block from any FEC_BLOCK of its fragments, whichever were
   lost. The PC asks for the share of parity it needs (0 to 100 percent of the data) as the loss on its line changes.

   One fragment, before it is sealed as a datagram (secure-rules.h), all numbers little-endian:
     0  u32 record number       4  u32 record size     8  u16 block     10 u8 index (data 0..k-1, parity k..k+m-1)
     11 u8 k (data fragments)   12 u8 m (parity)       13 u8 1          14 u16 0
     16 the fragment's bytes: data fragment i of a block holds the record's bytes from (block*FEC_BLOCK+i)*FEC_FRAGMENT, and a parity
        fragment is as long as the block's first data fragment, the shorter last fragment counted with zeros after it.
   Parity row j of a block, for data column i, has the coefficient 1/((FEC_BLOCK+j) xor i): the rows and the columns are all
   different numbers, so every square part of the matrix can be inverted, which is what lets any k fragments rebuild the block.

   Freestanding, with no library, so the same file builds into the payload and into the PC's tests. */
#ifndef FEC_RULES_H
#define FEC_RULES_H
#include <stddef.h>
#include <stdint.h>
#define FEC_FRAGMENT 1152u
#define FEC_BLOCK 32u
#define FEC_HEADER 16u
#define FEC_MOST_PERCENT 100u
/* A datagram's plain bytes at most: a header and a whole fragment. Sealed, with UDP and IP, 1224 bytes, which fits the 1280 every
   IPv6 path and a Tailscale tunnel carry. */
#define FEC_DATAGRAM (FEC_HEADER+FEC_FRAGMENT)
#define FEC_PART __attribute__((unused))

static unsigned char fec_exp[512],fec_log[256],fec_mul[256][256];static int fec_ready;
static void fec_init(void){
 if(fec_ready)return;
 unsigned x=1;
 for(int i=0;i<255;i++){fec_exp[i]=(unsigned char)x;fec_log[x]=(unsigned char)i;x<<=1;if(x&0x100)x^=0x11d;}
 for(int i=255;i<512;i++)fec_exp[i]=fec_exp[i-255];
 for(int a=1;a<256;a++)for(int b=1;b<256;b++)fec_mul[a][b]=fec_exp[fec_log[a]+fec_log[b]];
 fec_ready=1;
}
static unsigned char fec_coefficient(unsigned row,unsigned column){return fec_exp[255-fec_log[(FEC_BLOCK+row)^column]];}

struct fec_plan{uint32_t size,fragments,blocks;unsigned percent;};
FEC_PART static void fec_plan(struct fec_plan*p,uint32_t size,unsigned percent){
 p->size=size;p->fragments=(size+FEC_FRAGMENT-1)/FEC_FRAGMENT;p->blocks=(p->fragments+FEC_BLOCK-1)/FEC_BLOCK;
 p->percent=percent>FEC_MOST_PERCENT?FEC_MOST_PERCENT:percent;
}
/* The bytes of data fragment f of the record. */
static uint32_t fec_length(const struct fec_plan*p,uint32_t f){uint32_t at=f*FEC_FRAGMENT,left=p->size-at;return left<FEC_FRAGMENT?left:FEC_FRAGMENT;}
static unsigned fec_data_in(const struct fec_plan*p,uint32_t block){uint32_t left=p->fragments-block*FEC_BLOCK;return left<FEC_BLOCK?(unsigned)left:FEC_BLOCK;}
/* A block's parity: none at 0 percent, otherwise at least one and never more than its data. */
static unsigned fec_parity_in(const struct fec_plan*p,uint32_t block){
 unsigned k=fec_data_in(p,block);if(!p->percent)return 0;
 unsigned m=(k*p->percent+99)/100;return m<1?1:m>k?k:m;
}
/* The parity fragments of a block, one after another, each fec_length(first data fragment) long, into parity. */
FEC_PART static void fec_parity(const struct fec_plan*p,const unsigned char*record,uint32_t block,unsigned char*parity){
 unsigned k=fec_data_in(p,block),m=fec_parity_in(p,block);uint32_t first=block*FEC_BLOCK,width=fec_length(p,first);
 for(unsigned j=0;j<m;j++){
  unsigned char*out=parity+(size_t)j*width;for(uint32_t t=0;t<width;t++)out[t]=0;
  for(unsigned i=0;i<k;i++){
   const unsigned char*row=fec_mul[fec_coefficient(j,i)],*data=record+(size_t)(first+i)*FEC_FRAGMENT;uint32_t n=fec_length(p,first+i);
   for(uint32_t t=0;t<n;t++)out[t]^=row[data[t]];
  }
 }
}
/* Fragment index of a block (data first, then parity) with its header into out, which holds FEC_DATAGRAM bytes; returns its size.
   parity is what fec_parity wrote for this block. */
FEC_PART static size_t fec_fragment(const struct fec_plan*p,uint32_t number,const unsigned char*record,const unsigned char*parity,uint32_t block,unsigned index,unsigned char*out){
 unsigned k=fec_data_in(p,block),m=fec_parity_in(p,block);uint32_t first=block*FEC_BLOCK,width=fec_length(p,first);
 const unsigned char*from;uint32_t n;
 if(index<k){from=record+(size_t)(first+index)*FEC_FRAGMENT;n=fec_length(p,first+index);}
 else{from=parity+(size_t)(index-k)*width;n=width;}
 uint32_t size=p->size;
 for(int i=0;i<4;i++){out[i]=(unsigned char)(number>>(8*i));out[4+i]=(unsigned char)(size>>(8*i));}
 out[8]=(unsigned char)block;out[9]=(unsigned char)(block>>8);out[10]=(unsigned char)index;out[11]=(unsigned char)k;out[12]=(unsigned char)m;out[13]=1;out[14]=out[15]=0;
 for(uint32_t t=0;t<n;t++)out[FEC_HEADER+t]=from[t];
 return FEC_HEADER+n;
}

/* The PC's report, sent as a sealed datagram about four times a second: it says where to send the stream (its address, as the
   datagram came from) and how much parity it wants.
     0 'PBH1'   4 u8 parity percent   5..7 0   8 u32 records received   12 u32 records lost */
#define FEC_REPORT_SIZE 16
FEC_PART static int fec_report(const unsigned char*w,long n,unsigned*percent){
 if(n!=FEC_REPORT_SIZE||w[0]!='P'||w[1]!='B'||w[2]!='H'||w[3]!='1')return 0;
 *percent=w[4]>FEC_MOST_PERCENT?FEC_MOST_PERCENT:w[4];return 1;
}
#endif
