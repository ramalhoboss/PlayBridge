/* Capture options for the firmware-13.60 sender; u32/u64 come from the includer. */
#define RESOLUTION_1080P 4u
#define RESOLUTION_1440P 5u
#define RESOLUTION_2160P 6u
/* Bytes the encoder may spend on a frame before it skips frames to catch up: a frame costing N budgets loses N-1 frames.
   The official client's one-frame budget stalled the picture after every keyframe and lowered the frame rate, and the
   bitrate holds without it. 1.5 MB was accepted on a live 1080p capture; Start refuses 2 MiB with 0x80c78000. */
#define FRAME_BYTE_BUDGET 0x100000u
#define CODEC_H264 0u
#define CODEC_HEVC 1u
static int valid_target(uint32_t resolution,uint32_t bitrate,uint32_t codec){
 if(codec==CODEC_HEVC){
  if(resolution==RESOLUTION_1080P)return bitrate==8000000||bitrate==12000000||bitrate==16000000;
  if(resolution==RESOLUTION_1440P)return bitrate==15000000||bitrate==20000000||bitrate==30000000;
  if(resolution==RESOLUTION_2160P)return bitrate==20000000||bitrate==30000000||bitrate==40000000;
  return 0;
 }
 if(codec!=CODEC_H264)return 0;
 if(resolution==RESOLUTION_1080P)return bitrate==4000000||bitrate==8000000||bitrate==12000000||bitrate==16000000||bitrate==20000000||bitrate==30000000;
 if(resolution==RESOLUTION_1440P)return bitrate==20000000||bitrate==30000000||bitrate==50000000;
 if(resolution==RESOLUTION_2160P)return bitrate==40000000||bitrate==60000000||bitrate==80000000;
 return 0;
}
/* GetVideoOutMode mirrors the firmware's open checks: 0x20 allows 1440p, 0x08 allows 2160p. */
static uint32_t supported_resolution(uint32_t wanted,uint32_t output_mode){
 if(wanted>=RESOLUTION_2160P&&(output_mode&0x08))return RESOLUTION_2160P;
 if(wanted>=RESOLUTION_1440P&&(output_mode&0x20))return RESOLUTION_1440P;
 return RESOLUTION_1080P;
}
/* Resource Arbitrator components: 14 is the firmware's "ScanIn Test 2K", which is its 1080p class. */
static int resolution_profile(uint32_t resolution){return resolution==RESOLUTION_2160P?10:resolution==RESOLUTION_1440P?11:14;}
/* sceAvcap2ReadVideo results the official client answers by reopening the encoder. It treats every other negative as no frame this time.
   0x81950004 stays out of this list: it is counted as an overrun here and the stream carries on. */
#define READ_RAISE_QP 0x8195000du
#define REOPEN_LIMIT 3
#define NO_FRAME_REOPEN_US 3000000u
static int read_needs_reopen(uint32_t code){return code==0x81950003u||code==0x81950008u||code==0x81950009u||code==READ_RAISE_QP;}
/* Writes the resolution-dependent video parameters and returns the bitrate actually requested. */
static uint32_t apply_resolution(unsigned char*p,uint32_t resolution,uint32_t fps,uint32_t bitrate){
 uint32_t limit=resolution==RESOLUTION_2160P?80000000:resolution==RESOLUTION_1440P?50000000:30000000;
 uint32_t rate=bitrate<limit?bitrate:limit,frame_bits=(uint32_t)((uint64_t)rate*1001/(fps*1000));
 u32(p,0x18,resolution);u32(p,0x28,(uint32_t)resolution_profile(resolution));
 u32(p,0xc8,rate);u32(p,0xcc,rate);u32(p,0xd0,frame_bits);
 u32(p,0x10c,FRAME_BYTE_BUDGET);
 /* Image-paste buffer: the official client scales it with the resolution. The 1080p values are the ones tested live. */
 if(resolution==RESOLUTION_2160P){u32(p,0x20c,768);u32(p,0x210,720);u32(p,0x214,768);u64(p,0x218,0xcc000);}
 else if(resolution==RESOLUTION_1440P){u32(p,0x20c,512);u32(p,0x210,464);u32(p,0x214,512);u64(p,0x218,0x58000);}
 else{u32(p,0x20c,384);u32(p,0x210,320);u32(p,0x214,512);u64(p,0x218,0x3c000);}
 return rate;
}
/* sceAvcap2GetVideoHeader keeps up to three parameter sets, each a length followed by at most 128 bytes: H.264 fills two, HEVC three.
   Returns them with start codes, HEVC in NAL type order (VPS, SPS, PPS), or 0 when one is missing. */
#define CODEC_HEADERS_MAX 396u
static size_t codec_headers(unsigned char*out,const unsigned char*header,uint32_t codec){
 static const unsigned short lengths[3]={0x10,0x98,0x120},bodies[3]={0x18,0xa0,0x128};
 int count=codec==CODEC_HEVC?3:2,order[3]={0,1,2};
 for(int i=0;i<count;i++){uint64_t n;memcpy(&n,header+lengths[i],8);if(n==0||n>128)return 0;}
 if(codec==CODEC_HEVC)for(int i=1;i<count;i++)for(int j=i;j>0&&header[bodies[order[j-1]]]>header[bodies[order[j]]];j--){int t=order[j];order[j]=order[j-1];order[j-1]=t;}
 size_t at=0;
 for(int i=0;i<count;i++){uint64_t n;memcpy(&n,header+lengths[order[i]],8);out[at]=0;out[at+1]=0;out[at+2]=0;out[at+3]=1;at+=4;memcpy(out+at,header+bodies[order[i]],n);at+=n;}
 return at;
}
/* The access unit delimiter that starts each frame on the wire. */
static size_t delimiter(unsigned char*out,uint32_t codec){
 static const unsigned char h264[6]={0,0,0,1,9,0xf0},hevc[7]={0,0,0,1,0x46,1,0x50};
 if(codec==CODEC_HEVC){memcpy(out,hevc,7);return 7;}
 memcpy(out,h264,6);return 6;
}
