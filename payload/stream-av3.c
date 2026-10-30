#include <ps5/kernel.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
typedef int (*load_fn)(const char*,size_t,const void*,uint32_t,void*,int*);
static FILE *logf;
static uint32_t module(load_fn load,const char *name){uint32_t h=0; if(!kernel_dynlib_handle(-1,name,&h)&&h)return h; const char *roots[]={"/system/common/lib/","/system/priv/lib/","/system_ex/common_ex/lib/",0};for(int i=0;load&&roots[i];i++){char p[256];snprintf(p,sizeof p,"%s%s",roots[i],name);int result=0;int rv=load(p,0,0,0,0,&result);fprintf(logf,"load %s rv=%x result=%x\n",p,rv,result);fflush(logf);if(!kernel_dynlib_handle(-1,name,&h)&&h)return h;}return 0;}
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <netinet/in.h>
#include <poll.h>
#include <signal.h>
#include <errno.h>
#include <time.h>
#include <netinet/tcp.h>
static int client=-1;
static int send_all(const void*data,size_t length){const unsigned char*p=data;while(length){ssize_t n=send(client,p,length,0);if(n<=0)return -1;p+=n;length-=(size_t)n;}return 0;}
static int wait_client(void){signal(SIGPIPE,SIG_IGN);int s=socket(AF_INET,SOCK_STREAM,0);if(s<0)return -1;int one=1;setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&one,sizeof one);struct sockaddr_in a={0};a.sin_len=sizeof a;a.sin_family=AF_INET;a.sin_port=htons(9076);a.sin_addr.s_addr=htonl(INADDR_ANY);if(bind(s,(struct sockaddr*)&a,sizeof a)<0||listen(s,1)<0){close(s);return -1;}struct pollfd p={s,POLLIN,0};int n=poll(&p,1,60000);int fd=n>0?accept(s,0,0):-1;close(s);if(fd>=0){int snd=65536;setsockopt(fd,SOL_SOCKET,SO_SNDBUF,&snd,sizeof snd);int nd=1;setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,&nd,sizeof nd);struct timeval tv={1,0};setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&tv,sizeof tv);}return fd;}


#include "av-wire.h"
static void u32(unsigned char*p,int o,uint32_t v){memcpy(p+o,&v,4);}
static void u64(unsigned char*p,int o,uint64_t v){memcpy(p+o,&v,8);}
#include "capture-options.h"

static uint32_t capture_fps=60,capture_bitrate=8000000,requested_resolution=RESOLUTION_1080P,capture_resolution=RESOLUTION_1080P,capture_output_mode=0,refused_by=0;
static int resource_profile=14,options_received=0;
static int receive_options(void){
 struct pollfd p={client,POLLIN,0};int ready=poll(&p,1,250);
 if(ready==0)return 0;if(ready<0)return -1;
 struct timeval timeout={1,0};setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof timeout);
 unsigned char request[16];size_t got=0;
 while(got<sizeof request){ssize_t n=recv(client,request+got,sizeof request-got,0);if(n<=0)return -1;got+=(size_t)n;}
 uint32_t fps,bitrate,resolution;memcpy(&fps,request+4,4);memcpy(&bitrate,request+8,4);memcpy(&resolution,request+12,4);
 /* Receivers before the resolution option send 0 here. */
 if(!resolution)resolution=RESOLUTION_1080P;
 if(memcmp(request,"PBO1",4)||fps!=60||!valid_target(resolution,bitrate))return -1;
 capture_fps=fps;capture_bitrate=bitrate;requested_resolution=resolution;options_received=1;return 0;
}
static int capture_ack(void){
 if(!options_received)return 0;
 char body[256];int n=snprintf(body,sizeof body,"{\"protocol\":2,\"confirmed\":true,\"fps_target\":%u,\"bitrate_target\":%u,\"resource_profile\":%d,\"resolution\":%u,\"resolution_requested\":%u,\"output_mode\":%u,\"refused_by\":%u}",capture_fps,capture_bitrate,resource_profile,capture_resolution,requested_resolution,capture_output_mode,refused_by);
 if(n<=0||(size_t)n>=sizeof body)return -1;
 unsigned char header[32]={0};memcpy(header,"PSAV",4);header[4]=1;header[5]=3;uint32_t size=(uint32_t)n;memcpy(header+8,&size,4);
 return send_all(header,32)||send_all(body,(size_t)n)?-1:0;
}

#define LOG(...) do{fprintf(logf,__VA_ARGS__);fflush(logf);}while(0)
static void resource_callback(int id,int state,void *info){(void)id;(void)state;(void)info;}
static void use_resolution(unsigned char*p,uint32_t resolution){
 capture_resolution=resolution;resource_profile=resolution_profile(resolution);capture_bitrate=apply_resolution(p,resolution,capture_fps,capture_bitrate);
 /* 64 KiB is about 6 ms of an 80 Mbit/s stream. */
 int snd=resolution>RESOLUTION_1080P?262144:65536;setsockopt(client,SOL_SOCKET,SO_SNDBUF,&snd,sizeof snd);
 LOG("Capture resolution=%u requested=%u output_mode=%08x profile=%d bitrate=%u\n",capture_resolution,requested_resolution,capture_output_mode,resource_profile,capture_bitrate);
}
int main(void){logf=fopen("/data/ps5screen-av3.txt","w");if(!logf)return 1;LOG("PlayBridge capture v1.2 pid=%d fw=%08x\n",getpid(),kernel_get_fw_version());if(kernel_get_fw_version()!=0x13600007u){LOG("unsupported firmware\n");fclose(logf);return 9;}LOG("Listening TCP 9076 for 60 seconds...\n");client=wait_client();if(client<0){LOG("No viewer or socket error errno=%d\n",errno);fclose(logf);return 14;}LOG("Viewer connected\n");if(receive_options()<0){LOG("Invalid capture options\n");close(client);fclose(logf);return 15;}LOG("Capture request fps=%u bitrate=%u resolution=%u\n",capture_fps,capture_bitrate,requested_resolution);uint32_t kh=0;const char*ks[]={"libkernel_web.sprx","libkernel.sprx","libkernel_sys.sprx",0};for(int i=0;ks[i];i++)if(!kernel_dynlib_handle(-1,ks[i],&kh)&&kh)break;load_fn load=kh?(load_fn)kernel_dynlib_resolve(-1,kh,"wzvqT4UqKX8"):0;module(load,"libSceIpmi.sprx");uint32_t ah=module(load,"libSceAvcap2.sprx");if(!ah){fclose(logf);return 2;}
int(*Init)(void)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2Initialize");int(*Term)(void)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2Terminate");int(*Open)(int64_t*,void*,int)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2OpenVideo");int(*Start)(int64_t)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2Start");int(*Stop)(int64_t)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2Stop");int(*Close)(int64_t)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2Close");int(*Read)(int64_t,void*,size_t,void*,int)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2ReadVideo");if(!Init||!Term||!Open||!Start||!Stop||!Close||!Read){LOG("missing API\n");fclose(logf);return 3;}
int(*OpenAudio)(int64_t*,void*,int)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2OpenAudio");int(*ReadAudio)(int64_t,void*,size_t,void*,int)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2ReadAudio");
unsigned char p[0x2e8]={0};u64(p,0,0x2e8);u64(p,8,0x28);u32(p,0x14,2);u32(p,0x1c,1);u32(p,0x24,0);u64(p,0x30,0x58);u64(p,0x38,0x18);p[0x40]=1;u32(p,0x44,1);u32(p,0x48,1);u32(p,0x4c,0x200000);u64(p,0x50,0x10);p[0x58]=1;u32(p,0x5c,9);u64(p,0x60,0x18);p[0x68]=1;u64(p,0x88,0x30);u32(p,0x94,capture_fps);u64(p,0xb8,0xe8);u64(p,0xc0,0x20);u32(p,0xd8,0x33);u64(p,0xe0,0x20);u64(p,0x100,0x20);p[0x108]=1;u64(p,0x120,0x18);p[0x128]=1;u32(p,0x12c,25);u32(p,0x130,capture_fps);u64(p,0x188,0x10);p[0x190]=1;u32(p,0x194,1);u64(p,0x1a0,0x50);u32(p,0x1a8,0);u64(p,0x1f0,0xf8);u64(p,0x1f8,0x28);u64(p,0x220,0x88);/* Official client uses -1 sentinels for all optional image coefficients. */memset(p+0x228,0xff,0x80);u32(p,0x2ac,2);u64(p,0x2b0,0x10);u32(p,0x2b8,1);p[0x2bc]=1;u64(p,0x2c0,0x10);p[0x2c8]=1;u32(p,0x2cc,110);
LOG("Initialize...\n");int rv=Init();LOG("Initialize=%08x\n",rv);if(rv<0){fclose(logf);return 4;}uint32_t caps=0;int(*Caps)(uint32_t*)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2GetVideoOutMode");if(!Caps){Term();fclose(logf);return 10;}int cv=Caps(&caps);LOG("Caps=%08x value=%08x\n",cv,caps);if(cv<0){Term();fclose(logf);return 5;}u32(p,0x2a8,caps);capture_output_mode=caps;use_resolution(p,supported_resolution(requested_resolution,caps));
/* Firmware-specific entries corroborated against offline Resource2 Ghidra project.
 * Never read execute-only instructions inside this process. All resource state
 * is requested and released through the original client implementation. */
uint32_t rh=module(load,"libSceResourceArbitrator.sprx");uintptr_t base=rh?(uintptr_t)kernel_dynlib_mapbase_addr(-1,rh):0;
if(!base){Term();fclose(logf);return 11;}
int(*Register)(int,void(*)(int,int,void*),void*)=(void*)(base+0xdb0);
int(*Unregister)(int)=(void*)(base+0xee0);
int(*Request)(int,const char*,void*,int)=(void*)(base+0x10b0);
int(*CheckState)(int,const char*)=(void*)(base+0x1160);
int(*Channel)(int,int*,int*)=(void*)(base+0x1840);
/* A resolution the firmware still refuses steps down instead of ending the session. */
for(;;){int started=0;
int registered=Register(resource_profile,resource_callback,0);LOG("Resource register=%08x\n",registered);
if(registered<0){if(capture_resolution>RESOLUTION_1080P){refused_by=(uint32_t)registered;usleep(100000);use_resolution(p,supported_resolution(capture_resolution-1,caps));continue;}Term();fclose(logf);return 12;}
LOG("Resource state=%d\n",CheckState(resource_profile,"RUNNING"));int requested=Request(resource_profile,"RUNNING",0,getpid());LOG("Resource request=%08x\n",requested);
int channel=-1,mode=0;for(int i=0;requested>=0&&i<40;i++){int q=Channel(resource_profile,&channel,&mode);if(q<0||channel>=0)break;usleep(50000);}
LOG("Resource channel=%d mode=%d\n",channel,mode);
if(channel<0){LOG("Resource release=%08x\n",Request(resource_profile,"STOP",0,getpid()));LOG("Resource unregister=%08x\n",Unregister(resource_profile));if(capture_resolution>RESOLUTION_1080P){refused_by=requested<0?(uint32_t)requested:0xffffffffu;usleep(100000);use_resolution(p,supported_resolution(capture_resolution-1,caps));continue;}Term();fclose(logf);return 13;}
int64_t h=0;LOG("OpenVideo...\n");rv=Open(&h,p,0);LOG("OpenVideo=%08x handle=%llx\n",rv,(unsigned long long)h);if(rv>=0&&h){unsigned char header[0x1a8]={0};u64(header,0,0x1a8);uintptr_t ab=(uintptr_t)kernel_dynlib_mapbase_addr(-1,ah);int(*GetHeader)(int64_t,void*)=(void*)(ab+0x1450);int hr=GetHeader(h,header);LOG("GetHeader=%08x\n",hr);uint64_t sl=0,pl=0;memcpy(&sl,header+0x10,8);memcpy(&pl,header+0x98,8);unsigned char sc[4]={0,0,0,1};int header_ok=hr>=0&&sl>0&&sl<=128&&pl>0&&pl<=128;unsigned char codec[272];size_t cn=0;if(header_ok){memcpy(codec+cn,sc,4);cn+=4;memcpy(codec+cn,header+0x18,sl);cn+=sl;memcpy(codec+cn,sc,4);cn+=4;memcpy(codec+cn,header+0xa0,pl);cn+=pl;}if(tables()<0)header_ok=0;LOG("Start...\n");rv=header_ok?Start(h):-1;LOG("Start=%08x\n",rv);if(rv>=0){started=1;int64_t audio=0;int audio_started=0;unsigned char ap[56]={0};u64(ap,0,56);u64(ap,8,24);u32(ap,0x14,2);u32(ap,0x18,1);u32(ap,0x1c,0xffffffffu);u32(ap,0x28,128000);int ar=OpenAudio?OpenAudio(&audio,ap,0):-1;LOG("OpenAudio=%08x handle=%llx\n",ar,(unsigned long long)audio);if(ar>=0&&audio){ar=Start(audio);audio_started=ar>=0;LOG("StartAudio=%08x\n",ar);}unsigned char*buf=malloc(0x200000);unsigned char*vb=malloc(0x200200);int frames=0,packets=0,errors=0,overruns=0;size_t total=0;uint64_t began=mono_us(),vp0=0,vpn=0,ap0=0,apn=0;uint64_t max_call=0;int running=buf&&vb&&audio_started;if(running&&capture_ack()<0)running=0;while(running){int progress=0;for(int k=0;k<8&&running;k++){unsigned char abuf[8192],adts[8200];uint64_t am[2]={16,0};int n=ReadAudio(audio,abuf,sizeof abuf,am,1);if(n>0&&n<=8192){int size=n+7;adts[0]=0xff;adts[1]=0xf1;adts[2]=0x4c;adts[3]=0x80|(size>>11);adts[4]=size>>3;adts[5]=((size&7)<<5)|0x1f;adts[6]=0xfc;memcpy(adts+7,abuf,n);uint64_t t=am[1]*3/8;if(!packets)ap0=am[1];apn=am[1];if(pes(0x101,0xc0,adts,size,t,t,0)<0)running=0;packets++;progress=1;}else{if((uint32_t)n==0x81950004u)overruns++;else if(n<0&&(uint32_t)n!=0x81950002u){LOG("Audio error=%08x\n",n);errors++;running=0;}break;}}
unsigned char meta[0x70]={0};u64(meta,0,0x70);uint64_t call=mono_us();int n=Read(h,buf,0x200000,meta,1);call=mono_us()-call;if(call>max_call)max_call=call;if(n>0&&n<=0x200000){uint64_t pt=get64(meta,8),dt=get64(meta,16);if(frames<3){LOG("Video meta %d pts=%llu dts=%llu ageclock=%llu bytes=%d\n",frames,(unsigned long long)pt,(unsigned long long)dt,(unsigned long long)mono_us(),n);}if(!frames)vp0=pt;vpn=pt;size_t vn=0;unsigned char aud[6]={0,0,0,1,9,0xf0};memcpy(vb,aud,6);vn=6;if(frames%60==0){if(tables()<0)running=0;memcpy(vb+vn,codec,cn);vn+=cn;}memcpy(vb+vn,buf,n);vn+=n;if(pes(0x100,0xe0,vb,vn,pt*3/8,dt*3/8,1)<0)running=0;frames++;total+=n;progress=1;}else if((uint32_t)n==0x81950004u)overruns++;else if(n<0&&(uint32_t)n!=0x81950002u){LOG("Video error=%08x\n",n);errors++;running=0;}if(!progress)usleep(500);}
LOG("frames=%d audio_packets=%d bytes=%zu elapsed_us=%llu video_first=%llu video_last=%llu audio_first=%llu audio_last=%llu max_read_us=%llu overruns=%d errors=%d\n",frames,packets,total,(unsigned long long)(mono_us()-began),(unsigned long long)vp0,(unsigned long long)vpn,(unsigned long long)ap0,(unsigned long long)apn,(unsigned long long)max_call,overruns,errors);free(buf);free(vb);if(audio_started)LOG("StopAudio=%08x\n",Stop(audio));if(audio)LOG("CloseAudio=%08x\n",Close(audio));LOG("Stop=%08x\n",Stop(h));}LOG("Close=%08x\n",Close(h));}LOG("Resource release=%08x\n",Request(resource_profile,"STOP",0,getpid()));LOG("Resource unregister=%08x\n",Unregister(resource_profile));if(started||capture_resolution==RESOLUTION_1080P)break;refused_by=(uint32_t)rv;usleep(100000);use_resolution(p,supported_resolution(capture_resolution-1,caps));}LOG("Terminate=%08x\n",Term());close(client);fclose(logf);return 0;}
