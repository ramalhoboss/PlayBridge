/* The DualSense's microphone port. The console's own microphone library, libSceAudioIn, which games open for voice chat, gets the whole
   payload stopped by the system when a payload opens it (mic-rules.h), so the port only tells the PC that the microphone stays closed,
   on a thread and a port of their own as before. The code that opened and read it is kept behind PB_MIC_OPEN, which no build sets, for
   a way that runs as a title of its own. */
#include "mic-rules.h"
#ifdef PB_MIC_OPEN
typedef int(*mic_open_fn)(int,uint32_t,uint32_t,uint32_t,uint32_t,uint32_t);
static struct{mic_open_fn open,hq_open;int(*input)(int,void*);int(*close)(int);int(*silent)(int);}mic;
/* The way that opened the microphone, or the console's error of the last one tried. */
static int mic_open_way(int user,int*rate,int*way){
 int last=-1;
 for(int i=0;i<MIC_WAYS;i++){
  int who=mic_ways[i].system?MIC_SYSTEM_USER:user;mic_open_fn open=mic_ways[i].hq?mic.hq_open:mic.open;
  if(!open||who<0)continue;
  /* Written down before the call as well, so a log that ends here names the way that never came back. */
  CLOG("mic way %d opening...\n",i);uint64_t at=mono_us();
  int handle=open(who,(uint32_t)mic_ways[i].type,0,MIC_GRAIN,(uint32_t)mic_ways[i].rate,MIC_S16_MONO);
  CLOG("mic way %d (%s type %d, %d Hz, user %d): %08x after %llu ms\n",i,mic_ways[i].hq?"hq":"open",mic_ways[i].type,mic_ways[i].rate,who,(uint32_t)handle,(unsigned long long)(mono_us()-at)/1000);
  if(handle>=0){*rate=mic_ways[i].rate;*way=i;return handle;}
  last=handle;
 }
 return last;
}
#endif
static void mic_serve(int fd){
 struct timeval limit={2,0};setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&limit,sizeof limit);int nd=1;setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,&nd,sizeof nd);
#ifndef PB_MIC_OPEN
 unsigned char answer[MIC_HEAD];mic_head(answer,(int)MIC_STAYS_CLOSED,0,-1);
 if(link_write(&mic_link,fd,answer,sizeof answer)<0)CLOG("mic: the answer did not go, errno=%d\n",errno);
 else CLOG("mic: told the PC that the microphone stays closed\n");
#else
 int user=-1;if(mic.open&&mic.input&&mic.close){CLOG("mic: foreground user...\n");user=foreground_user();CLOG("mic: foreground user %d\n",user);}
 int rate=0,way=-1,handle=mic.open&&mic.input&&mic.close?mic_open_way(user,&rate,&way):-ENOSYS;
 unsigned char head[MIC_HEAD];mic_head(head,handle,rate,way);
 if(link_write(&mic_link,fd,head,sizeof head)<0||handle<0){CLOG("mic: not opened (%08x) or the answer did not go, errno=%d\n",(uint32_t)handle,errno);if(handle>=0)mic.close(handle);return;}
 static int16_t block[(MIC_BLOCK_HEAD/2)+MIC_GRAIN];int silent=0,failed=0;uint32_t blocks=0;
 uint64_t start=mono_us(),block_us=1000000ULL*MIC_GRAIN/(uint64_t)rate;
 for(;;){
  /* The first reads are written down with their answer and time, as XPS5 does: the call blocks, or not, for the block's time. */
  uint64_t at=mono_us();if(blocks<3)CLOG("mic block %u reading...\n",blocks);
  int got=mic.input(handle,block+MIC_BLOCK_HEAD/2);
  if(blocks<3)CLOG("mic block %u: %d after %llu us\n",blocks,got,(unsigned long long)(mono_us()-at));
  if(got<0){failed=got;break;}
  blocks++;
  /* A read that does not wait for the microphone would turn here without end, so it waits for the block's time itself. */
  if(mono_us()-start+200000<blocks*block_us)usleep((useconds_t)block_us);
  if(blocks%30==1&&mic.silent){int now=mic.silent(handle);if(now>=0&&now!=silent){CLOG("mic silent state %x after %u blocks\n",now,blocks);silent=now;}}
  mic_block_head((unsigned char*)block,silent);
  if(link_write(&mic_link,fd,block,sizeof block)<0){CLOG("mic: send failed errno=%d\n",errno);break;}
 }
 CLOG("mic closing...\n");
 CLOG("mic closed %08x after %u blocks, read error %08x\n",(uint32_t)mic.close(handle),blocks,(uint32_t)failed);
#endif
}
static void*mic_thread(void*unused){(void)unused;
 int listener=control_socket(MIC_PORT);CLOG("mic listener=%d errno=%d\n",listener,errno);
 if(listener<0)return 0;
 for(;;){
  int fd=accept(listener,0,0);if(fd<0){if(errno==EINTR)continue;CLOG("mic: accept errno=%d\n",errno);return 0;}
  uint32_t peer=link_peer(fd);char at[16];secure_address(peer,at);
  /* The port answers only the PC that proved the key. */
  if(!away_admit(secure_on,peer)){CLOG("mic: %s, outside the home network, was closed\n",at);close(fd);continue;}
  if(secure_on){
   uint64_t began=secure_now_ms();int proved=secure_accept(&mic_link,fd,SECURE_MIC);
   if(proved<0){CLOG("mic: %s did not prove the key: %s errno=%d after %llu ms\n",at,secure_failure(proved),errno,(unsigned long long)(secure_now_ms()-began));close(fd);continue;}
   CLOG("mic: %s proved the key in %llu ms\n",at,(unsigned long long)(secure_now_ms()-began));
  }
  else CLOG("mic: %s connected\n",at);
  mic_serve(fd);link_end(&mic_link);close(fd);
 }
}
/* On the main thread, as every symbol is looked up (console-control.h). Without PB_MIC_OPEN libSceAudioIn is not even loaded. */
static void mic_start(load_fn load){
#ifdef PB_MIC_OPEN
 uint32_t library=module(load,"libSceAudioIn.sprx");
 mic.open=(mic_open_fn)symbol(library,"sceAudioInOpen");mic.hq_open=(mic_open_fn)symbol(library,"sceAudioInHqOpen");
 mic.input=symbol(library,"sceAudioInInput");mic.close=symbol(library,"sceAudioInClose");mic.silent=symbol(library,"sceAudioInGetSilentState");
#else
 (void)load;
#endif
 helper_thread(mic_thread,"mic");
}
