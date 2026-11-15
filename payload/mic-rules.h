/* The DualSense microphone's port and what goes over it. No console calls here, so the PC tests read this file. */
#define MIC_PORT 9079
#define MIC_MAGIC "PBM1"
/* Samples a block: 16 ms at 16 kHz. */
#define MIC_GRAIN 256
#define MIC_S16_MONO 0
/* The system's user, as the audio ports take it. */
#define MIC_SYSTEM_USER 0xff
enum{MIC_VOICE_CHAT=0,MIC_GENERAL=1,MIC_VOICE_RECOGNITION=5};
/* The ways to open the microphone, tried in order until one opens: the user's own voice chat first, as games open it. The same order
   the owner's XPS5 app tries. */
static const struct{int hq,type,rate,system;}mic_ways[]={
 {0,MIC_VOICE_CHAT,16000,0},{0,MIC_GENERAL,16000,0},{0,MIC_GENERAL,48000,0},{0,MIC_VOICE_RECOGNITION,16000,0},{1,MIC_VOICE_CHAT,48000,0},{0,MIC_GENERAL,16000,1}};
#define MIC_WAYS ((int)(sizeof mic_ways/sizeof mic_ways[0]))
/* The answer once the PC connects: "PBM1", then the port's handle or the console's error, the samples a second, the samples a block and
   the way that opened it (-1 when none did), each a 32-bit number. After it, each block: its samples and the silent flags of
   sceAudioInGetSilentState (16 bits each), then the samples, 16-bit mono. */
#define MIC_HEAD 20u
#define MIC_BLOCK_HEAD 4u
static void mic_head(unsigned char out[MIC_HEAD],int handle,int rate,int way){
 int32_t v[4]={handle,rate,MIC_GRAIN,way};memcpy(out,MIC_MAGIC,4);memcpy(out+4,v,sizeof v);
}
static void mic_block_head(unsigned char out[MIC_BLOCK_HEAD],int silent){
 uint16_t v[2]={MIC_GRAIN,(uint16_t)(silent<0?0:silent)};memcpy(out,v,sizeof v);
}
