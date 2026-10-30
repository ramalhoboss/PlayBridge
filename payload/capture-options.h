/* Capture options for the firmware-13.60 sender; u32/u64 come from the includer. */
#define RESOLUTION_1080P 4u
#define RESOLUTION_1440P 5u
#define RESOLUTION_2160P 6u
/* Bytes the encoder may spend on a frame before it skips frames to catch up: a frame costing N budgets loses N-1 frames.
   The official client's one-frame budget stalled the picture after every keyframe and lowered the frame rate, and the
   bitrate holds without it. 1.5 MB was accepted on a live 1080p capture; Start refuses 2 MiB with 0x80c78000. */
#define FRAME_BYTE_BUDGET 0x100000u
static int valid_target(uint32_t resolution,uint32_t bitrate){
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
