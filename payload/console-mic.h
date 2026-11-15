/* The DualSense's microphone, for recordings, instant replays and Go live on the PC. The console's own microphone library,
   libSceAudioIn, which games open for voice chat, is opened only while the PC listens on MIC_PORT, on a thread and a port of their own,
   so nothing it waits for can hold up the picture, the sound or the control port. When the PC leaves, the microphone closes. */
#include "mic-rules.h"
typedef int(*mic_open_fn)(int,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
static struct{mic_open_fn open,hq_open;int(*input)(int,void*);int(*close)(int);int(*silent)(int);}mic;
/* The way that opened the microphone, or the console's error of the last one tried. */
static int mic_open_way(int user,int*rate,int*way){
 int last=-1;
 for(int i=0;i<MIC_WAYS;i++){
  int who=mic_ways[i].system?MIC_SYSTEM_USER:user;mic_open_fn open=mic_ways[i].hq?mic.hq_open:mic.open;
  if(!open||who<0)continue;
  int handle=open(who,(uint32_t)mic_ways[i].type,0,MIC_GRAIN,(uint32_t)mic_ways[i].rate,MIC_S16_MONO);
  CLOG("mic way %d (%s type %d, %d Hz, user %d): %08x\n",i,mic_ways[i].hq?"hq":"open",mic_ways[i].type,mic_ways[i].rate,who,(uint32_t)handle);
  if(handle>=0){*rate=mic_ways[i].rate;*way=i;return handle;}
  last=handle;
 }
 return last;
}
static void mic_serve(int fd){
 struct timeval limit={2,0};setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&limit,sizeof limit);int nd=1;setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,&nd,sizeof nd);
 int rate=0,way=-1,handle=mic.open&&mic.input&&mic.close?mic_open_way(foreground_user(),&rate,&way):-ENOSYS;
 unsigned char head[MIC_HEAD];mic_head(head,handle,rate,way);
 if(control_write(fd,head,sizeof head)<0||handle<0){if(handle>=0)mic.close(handle);return;}
 static int16_t block[(MIC_BLOCK_HEAD/2)+MIC_GRAIN];int silent=0,failed=0;uint32_t blocks=0;
 uint64_t start=mono_us(),block_us=1000000ULL*MIC_GRAIN/(uint64_t)rate;
 for(;;){
  int got=mic.input(handle,block+MIC_BLOCK_HEAD/2);
  if(got<0){failed=got;break;}
  blocks++;
  /* A read that does not wait for the microphone would turn here without end, so it waits for the block's time itself. */
  if(mono_us()-start+200000<blocks*block_us)usleep((useconds_t)block_us);
  if(blocks%30==1&&mic.silent){int now=mic.silent(handle);if(now>=0&&now!=silent){CLOG("mic silent state %x after %u blocks\n",now,blocks);silent=now;}}
  mic_block_head((unsigned char*)block,silent);
  if(control_write(fd,block,sizeof block)<0)break;
 }
 CLOG("mic closed %08x after %u blocks, read error %08x\n",(uint32_t)mic.close(handle),blocks,(uint32_t)failed);
}
static void*mic_thread(void*unused){(void)unused;
 int listener=control_socket(MIC_PORT);CLOG("mic listener=%d errno=%d\n",listener,errno);
 if(listener<0)return 0;
 for(;;){int fd=accept(listener,0,0);if(fd<0){if(errno==EINTR)continue;return 0;}mic_serve(fd);close(fd);}
}
/* On the main thread, as every symbol is looked up (console-control.h). Without the library the PC hears why and the rest carries on. */
static void mic_start(load_fn load){
 uint32_t library=module(load,"libSceAudioIn.sprx");
 mic.open=(mic_open_fn)symbol(library,"sceAudioInOpen");mic.hq_open=(mic_open_fn)symbol(library,"sceAudioInHqOpen");
 mic.input=symbol(library,"sceAudioInInput");mic.close=symbol(library,"sceAudioInClose");mic.silent=symbol(library,"sceAudioInGetSilentState");
 pthread_t thread;if(pthread_create(&thread,0,mic_thread,0)==0)pthread_detach(thread);
}
