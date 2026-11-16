#include <ps5/kernel.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <netinet/in.h>
#include <poll.h>
#include <signal.h>
#include <errno.h>
#include <time.h>
#include <netinet/tcp.h>
#include "secure-link.h"
#include "video-udp.h"
typedef int (*load_fn)(const char*,size_t,const void*,uint32_t,void*,int*);
static FILE *logf;
static uint32_t module(load_fn load,const char *name){uint32_t h=0; if(!kernel_dynlib_handle(-1,name,&h)&&h)return h; const char *roots[]={"/system/common/lib/","/system/priv/lib/","/system_ex/common_ex/lib/",0};for(int i=0;load&&roots[i];i++){char p[256];snprintf(p,sizeof p,"%s%s",roots[i],name);int result=0;int rv=load(p,0,0,0,0,&result);secure_log(logf,"capture","load %s rv=%x result=%x\n",p,rv,result);if(!kernel_dynlib_handle(-1,name,&h)&&h)return h;}return 0;}
static int client=-1;
/* The viewer's connection, sealed when this payload holds the PC's key. */
static struct secure_link video_link;
static int send_all(const void*data,size_t length){return link_write(&video_link,client,data,length);}
/* The stream over UDP, when the PC asked for it (video-udp.h): ready once its port is open, in use once the acknowledgement went. */
static struct video_udp video_udp={.fd=-1};static int want_udp,udp_ready,udp_mode;static unsigned char*udp_record;
/* Set by the PC's request to end play away from home (console-control.h): the payload leaves once no stream is running. */
static volatile int away_end;
/* How long to wait for a viewer: a minute after the upload, the away hours after a stream (away-rules.h). */
static uint64_t viewer_wait_ms=60000;
/* One record (a PSAV header and its packet): over TCP as before, or over UDP once the stream goes that way. */
static int send_record(const unsigned char head[32],const unsigned char*data,size_t n){
 if(!udp_mode)return send_all(head,32)||send_all(data,n)?-1:0;
 if(n>0x200200)return -1;
 if(!udp_record&&!(udp_record=malloc(32+0x200200)))return -1;
 memcpy(udp_record,head,32);memcpy(udp_record+32,data,n);return video_udp_send(&video_udp,udp_record,(uint32_t)(32+n));
}
static int viewer_listener=-1;
static int open_listener(void){signal(SIGPIPE,SIG_IGN);int s=socket(AF_INET,SOCK_STREAM,0);if(s<0)return -1;int one=1;setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&one,sizeof one);struct sockaddr_in a={0};a.sin_len=sizeof a;a.sin_family=AF_INET;a.sin_port=htons(9076);a.sin_addr.s_addr=htonl(INADDR_ANY);if(bind(s,(struct sockaddr*)&a,sizeof a)<0||listen(s,1)<0){close(s);return -1;}return s;}
/* Waits in slices, so the PC's request to end play away from home is seen within one. */
static int accept_viewer(int timeout_ms){
 uint64_t end=secure_now_ms()+(uint64_t)timeout_ms;int n=0;
 for(;;){uint64_t now=secure_now_ms();if(now>=end||away_end)return -1;uint64_t left=end-now;struct pollfd p={viewer_listener,POLLIN,0};n=poll(&p,1,left<AWAY_SLICE_MS?(int)left:AWAY_SLICE_MS);if(n>0||(n<0&&errno!=EINTR))break;}
 int fd=n>0?accept(viewer_listener,0,0):-1;if(fd>=0){int snd=65536;setsockopt(fd,SOL_SOCKET,SO_SNDBUF,&snd,sizeof snd);int nd=1;setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,&nd,sizeof nd);struct timeval tv={1,0};setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&tv,sizeof tv);}return fd;}


#include "av-wire.h"
static void u32(unsigned char*p,int o,uint32_t v){memcpy(p+o,&v,4);}
static void u64(unsigned char*p,int o,uint64_t v){memcpy(p+o,&v,8);}
#include "capture-options.h"

static uint32_t capture_fps=60,capture_bitrate=8000000,requested_resolution=RESOLUTION_1080P,capture_resolution=RESOLUTION_1080P,capture_output_mode=0,refused_by=0,capture_codec=CODEC_H264;
static int resource_profile=14,options_received=0,notify_viewer=0,viewer_connected=0,helpers_started=0;
/* A notice in the PS5's corner, as the system shows one: a 3120-byte request whose text starts at byte 45, the rest zero. Only
   when the PC asked for notices. */
struct notification_request{unsigned char head[45];char text[3075];};
int sceKernelSendNotificationRequest(int,struct notification_request*,size_t,int);
static int notice(const char*text){static struct notification_request request;if(!notify_viewer)return 0;memset(&request,0,sizeof request);snprintf(request.text,sizeof request.text,"%s",text);return sceKernelSendNotificationRequest(0,&request,sizeof request,0);}
static int receive_options(void){
 /* A PC that proved the key sends its options at once; over the internet they can take longer than on the home network. */
 struct pollfd p={client,POLLIN,0};int ready=poll(&p,1,secure_on?SECURE_WAIT_MS:250);
 if(ready==0)return secure_on?OPTIONS_DROPPED:OPTIONS_READ;if(ready<0)return OPTIONS_DROPPED;
 struct timeval timeout={1,0};setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,&timeout,sizeof timeout);
 unsigned char request[16];
 if(link_read(&video_link,client,request,sizeof request)<0)return OPTIONS_DROPPED;
 uint32_t fps,bitrate,resolution;memcpy(&fps,request+4,4);memcpy(&bitrate,request+8,4);memcpy(&resolution,request+12,4);
 /* The low byte is the resolution, the next one the codec and the rest flags. Receivers before the resolution option send 0 here. */
 uint32_t codec,flags;int known=split_target(resolution,&resolution,&codec,&flags);
 if(!resolution)resolution=RESOLUTION_1080P;
 if(memcmp(request,"PBO1",4)||fps!=60||!known||!valid_target(resolution,bitrate,codec))return OPTIONS_INVALID;
 capture_fps=fps;capture_bitrate=bitrate;requested_resolution=resolution;capture_codec=codec;notify_viewer=(flags&OPTION_NOTIFY)!=0;want_udp=(flags&OPTION_UDP)!=0;options_received=1;return OPTIONS_READ;
}
/* With the PC's key, a connection that does not prove it is dropped like one that sent nothing, and the wait goes on. */
/* Without a key, only a home address is a viewer (away-rules.h). */
static int viewer_options(int fd){
 client=fd;uint32_t peer=link_peer(fd);char at[16];
 if(!away_admit(secure_on,peer)){secure_log(logf,"capture","A viewer from outside the home network was closed\n");return OPTIONS_DROPPED;}
 if(secure_on){
  uint64_t began=secure_now_ms();int proved=secure_accept(&video_link,fd,SECURE_VIDEO);
  if(proved<0){secure_log(logf,"capture","Viewer %s did not prove the key: %s errno=%d after %llu ms\n",secure_address(peer,at),secure_failure(proved),errno,(unsigned long long)(secure_now_ms()-began));return OPTIONS_DROPPED;}
  secure_log(logf,"capture","Viewer %s proved the key in %llu ms\n",secure_address(peer,at),(unsigned long long)(secure_now_ms()-began));
 }
 int read=receive_options();
 if(read!=OPTIONS_READ)secure_log(logf,"capture","Viewer options: %s errno=%d\n",read==OPTIONS_DROPPED?"none came":"not valid",errno);
 return read;
}
static void drop_viewer(int fd){link_end(&video_link);close(fd);client=-1;}
static uint64_t now_ms(void){return mono_us()/1000;}
static int capture_ack(void){
 if(!options_received)return 0;
 char body[320];int n=snprintf(body,sizeof body,"{\"protocol\":2,\"confirmed\":true,\"fps_target\":%u,\"bitrate_target\":%u,\"resource_profile\":%d,\"resolution\":%u,\"resolution_requested\":%u,\"output_mode\":%u,\"refused_by\":%u,\"codec\":%u,\"control\":1,\"transport\":\"%s\",\"away\":%d}",capture_fps,capture_bitrate,resource_profile,capture_resolution,requested_resolution,capture_output_mode,refused_by,capture_codec,udp_ready?"udp":"tcp",away_on(secure_on,secure_flags));
 if(n<=0||(size_t)n>=sizeof body)return -1;
 unsigned char header[32]={0};memcpy(header,"PSAV",4);header[4]=1;header[5]=3;uint32_t size=(uint32_t)n;memcpy(header+8,&size,4);
 /* The first acknowledgement goes over TCP, and says the stream goes over UDP from then on; one after a reopen goes the stream's way. */
 if(send_record(header,(const unsigned char*)body,(size_t)n)<0)return -1;
 if(udp_ready&&!udp_mode){udp_mode=1;video_udp.started_ms=secure_now_ms();}
 return 0;
}

#define LOG(...) secure_log(logf,"capture",__VA_ARGS__)
/* The first send to the PC that failed in a stream, written down with its reason: EAGAIN when the PC stopped reading for the 1 s the
   send may wait, a reset when it left. */
static int send_failed_told;
static int sent(int result){if(result<0&&!send_failed_told){send_failed_told=1;LOG("Send to the PC failed errno=%d\n",errno);}return result;}
/* With trace on, once a second: how the capture loop stands, so a test sees when a stream stops and whether reading or sending stopped. */
static void capture_tick(int frames,int packets,int overruns,int errors,uint64_t max_call){
 static uint64_t at;if(!secure_trace)return;uint64_t now=mono_us();if(now-at<1000000)return;at=now;
 secure_log(0,"capture","tick frames=%d audio=%d overruns=%d errors=%d max_read_us=%llu\n",frames,packets,overruns,errors,(unsigned long long)max_call);
}
/* Ends this capture run: the loop around it opens the capture again, or the session ends once the limit is reached. */
#define REOPEN_OR_END() do{if(reopens<REOPEN_LIMIT){reopens++;reopen=1;}running=0;}while(0)
#include "console-control.h"
#include "console-mic.h"
static void resource_callback(int id,int state,void *info){(void)id;(void)state;(void)info;}
static void use_resolution(unsigned char*p,uint32_t resolution){
 capture_resolution=resolution;resource_profile=resolution_profile(resolution);capture_bitrate=apply_resolution(p,resolution,capture_fps,capture_bitrate);
 /* 64 KiB is about 6 ms of an 80 Mbit/s stream. */
 int snd=resolution>RESOLUTION_1080P?262144:65536;setsockopt(client,SOL_SOCKET,SO_SNDBUF,&snd,sizeof snd);
 LOG("Capture resolution=%u requested=%u output_mode=%08x profile=%d bitrate=%u\n",capture_resolution,requested_resolution,capture_output_mode,resource_profile,capture_bitrate);
}
static void wait_ms(int ms){usleep((useconds_t)ms*1000u);}
/* Over UDP nothing fails when the PC goes: it is gone once its reports stop, or once it closed the TCP connection. */
static int udp_alive(void){
 static uint64_t checked;uint64_t now=secure_now_ms();if(now-checked<20)return 1;checked=now;
 video_udp_poll(&video_udp,now);
 if(!away_pc_heard(now,video_udp.started_ms,video_udp.heard_ms)){LOG("UDP: the PC went quiet\n");return 0;}
 struct pollfd p={client,POLLIN,0};
 if(poll(&p,1,0)>0){unsigned char b;ssize_t r=recv(client,&b,1,MSG_PEEK|MSG_DONTWAIT);if(r==0||(r<0&&errno!=EAGAIN&&errno!=EINTR)){LOG("UDP: the PC closed its connection\n");return 0;}}
 return 1;
}
/* Writes one answer of the capture service's status query, all 32 bytes, so the log shows what each byte did. */
static void log_answer(const char*name,uint32_t result,const unsigned char*answer){
 char hex[2*CAPTURE_STATUS_BYTES+1];for(int i=0;i<CAPTURE_STATUS_BYTES;i++)snprintf(hex+2*i,3,"%02x",answer[i]);
 LOG("%s=%08x can_open=%s answer=%s\n",name,result,answer[CAPTURE_NOT_READY_BYTE]?"no":"yes",hex);
}
/* sceAvcap2ReadAudio hands over one packet per read, and one larger than the buffer gives 0x81950001 without moving on, so every
   read after it fails the same way and the capture is reopened for nothing. 64 KB holds any packet it makes (12-channel float is
   48 KB); AAC frames are far smaller, and one too large for ADTS (8191 bytes with its 7-byte header) is counted and skipped. */
#define AUDIO_READ_BYTES 65536
#define ADTS_MAX_FRAME 8191
/* The kernel's own module loader, for the system libraries the capture and the helpers need. */
static load_fn kernel_loader(void){
 uint32_t kh=0;const char*ks[]={"libkernel_web.sprx","libkernel.sprx","libkernel_sys.sprx",0};
 for(int i=0;ks[i];i++)if(!kernel_dynlib_handle(-1,ks[i],&kh)&&kh)break;
 return kh?(load_fn)kernel_dynlib_resolve(-1,kh,"wzvqT4UqKX8"):0;
}
/* The control port and the microphone start once, on the main thread, as their symbols must be looked up there. */
static void helpers_begin(load_fn load){
 module(load,"libSceIpmi.sprx");
 if(!helpers_started){helpers_started=1;control_start(load);mic_start(load);}
}
static int stream_main(void){logf=fopen("/data/ps5screen-av3.txt","w");if(!logf)return 1;LOG("PlayBridge capture v1.3 pid=%d fw=%08x\n",getpid(),kernel_get_fw_version());if(kernel_get_fw_version()!=0x13600007u){LOG("unsupported firmware\n");fclose(logf);return 9;}secure_start();send_failed_told=0;LOG("Secured: %s\n",secure_on?"yes, only the PC that sent this payload connects":"no, a payload loaded by hand");LOG("Listening TCP 9076 for %llu seconds...\n",(unsigned long long)(viewer_wait_ms/1000));viewer_listener=open_listener();if(viewer_listener<0){LOG("No viewer or socket error errno=%d\n",errno);fclose(logf);return 14;}
/* Away from home the control port opens with the wait, so the PC can end a waiting payload that never streamed. */
if(away_on(secure_on,secure_flags))helpers_begin(kernel_loader());
{struct viewer_calls vc={accept_viewer,viewer_options,drop_viewer,now_ms,viewer_wait_ms};int dropped=0,invalid=-1;int fd=first_viewer(&vc,&dropped,&invalid);close(viewer_listener);viewer_listener=-1;
if(dropped)LOG("Dropped %d connection(s) that closed before sending options\n",dropped);
if(fd==VIEWER_INVALID){LOG("Invalid capture options\n");close(invalid);fclose(logf);return 15;}
if(fd<0){LOG("No viewer or socket error errno=%d\n",errno);fclose(logf);return 14;}
client=fd;}
LOG("Viewer connected\n");if(want_udp&&secure_on&&video_link.live){video_udp_keys(&video_udp,secure_key,video_link.ns,video_link.nc,secure_now_ms());udp_ready=video_udp_open(&video_udp,capture_bitrate)==0;LOG("UDP stream: %s\n",udp_ready?"open":"not available, staying on TCP");}viewer_connected=1;if(notify_viewer)LOG("Notice=%08x\n",(uint32_t)notice("PlayBridge is streaming to your PC."));LOG("Capture request fps=%u bitrate=%u resolution=%u\n",capture_fps,capture_bitrate,requested_resolution);load_fn load=kernel_loader();helpers_begin(load);uint32_t ah=module(load,"libSceAvcap2.sprx");if(!ah){fclose(logf);return 2;}
int(*Init)(void)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2Initialize");int(*Term)(void)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2Terminate");int(*Open)(int64_t*,void*,int)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2OpenVideo");int(*Start)(int64_t)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2Start");int(*Stop)(int64_t)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2Stop");int(*Close)(int64_t)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2Close");int(*Read)(int64_t,void*,size_t,void*,int)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2ReadVideo");
/* GetVideoHeader and the status query have no name this payload can look up, so they are found by their place in libSceAvcap2 on 13.60. */
uintptr_t ab=(uintptr_t)kernel_dynlib_mapbase_addr(-1,ah);int(*Status)(void*)=ab?(void*)(ab+0x1750):0;
if(!Init||!Term||!Open||!Start||!Stop||!Close||!Read||!Status){LOG("missing API\n");fclose(logf);return 3;}
int(*OpenAudio)(int64_t*,void*,int)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2OpenAudio");int(*ReadAudio)(int64_t,void*,size_t,void*,int)=(void*)kernel_dynlib_dlsym(-1,ah,"sceAvcap2ReadAudio");
unsigned char p[0x2e8]={0};u64(p,0,0x2e8);u64(p,8,0x28);u32(p,0x14,2);/* HEVC opens with 1 here too, but the encoder only starts with 2. */u32(p,0x1c,capture_codec==CODEC_HEVC?2:1);u32(p,0x24,capture_codec);u64(p,0x30,0x58);u64(p,0x38,0x18);p[0x40]=1;u32(p,0x44,1);u32(p,0x48,1);u32(p,0x4c,0x200000);u64(p,0x50,0x10);p[0x58]=1;u32(p,0x5c,9);u64(p,0x60,0x18);p[0x68]=1;u64(p,0x88,0x30);u32(p,0x94,capture_fps);u64(p,0xb8,0xe8);u64(p,0xc0,0x20);u32(p,0xd8,0x33);u64(p,0xe0,0x20);u64(p,0x100,0x20);p[0x108]=1;u64(p,0x120,0x18);p[0x128]=1;u32(p,0x12c,25);u32(p,0x130,capture_fps);u64(p,0x188,0x10);p[0x190]=1;u32(p,0x194,1);u64(p,0x1a0,0x50);u32(p,0x1a8,0);u64(p,0x1f0,0xf8);u64(p,0x1f8,0x28);u64(p,0x220,0x88);/* Official client uses -1 sentinels for all optional image coefficients. */memset(p+0x228,0xff,0x80);u32(p,0x2ac,2);u64(p,0x2b0,0x10);u32(p,0x2b8,1);p[0x2bc]=1;u64(p,0x2c0,0x10);p[0x2c8]=1;u32(p,0x2cc,110);
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
/* The first open stays as before; the status is only written down, to compare with what a reopen sees. */
{unsigned char answer[CAPTURE_STATUS_BYTES]={0};log_answer("Status",(uint32_t)Status(answer),answer);}
struct capture_calls calls={Caps,Status,Open,wait_ms};
int reopen,reopens=0,again=0;do{reopen=0;int64_t h=0;
if(again){struct reopen_report report={0};LOG("OpenVideo when the capture can open...\n");rv=(int)open_when_ready(&calls,&h,p,capture_resolution,&caps,&report);capture_output_mode=caps;LOG("Waited %d ms: checks=%d cannot_open=%d busy=%d output_mode=%08x\n",report.waited_ms,report.checks,report.not_ready,report.busy,caps);if(report.checks){log_answer("Status first",report.first_result,report.first);log_answer("Status last",report.last_result,report.last);}}
else{LOG("OpenVideo...\n");rv=Open(&h,p,0);}
LOG("OpenVideo=%08x handle=%llx\n",rv,(unsigned long long)h);if(rv>=0&&h){unsigned char header[0x1a8]={0};u64(header,0,0x1a8);int(*GetHeader)(int64_t,void*)=(void*)(ab+0x1450);int hr=GetHeader(h,header);LOG("GetHeader=%08x\n",hr);unsigned char codec[CODEC_HEADERS_MAX];size_t cn=codec_headers(codec,header,capture_codec);int header_ok=hr>=0&&cn>0;LOG("Codec=%u headers=%zu first=%02x %02x %02x\n",capture_codec,cn,header[0x18],header[0xa0],header[0x128]);if(tables()<0)header_ok=0;if(header_ok&&udp_ready&&!video_udp.peer){uint64_t asked=secure_now_ms();int heard=video_udp_wait_peer(&video_udp,secure_now_ms,UDP_FIRST_REPORT_WAIT_MS);LOG("UDP: the PC's first report %s after %llu ms\n",heard?"came":"did not come",(unsigned long long)(secure_now_ms()-asked));}LOG("Start...\n");rv=header_ok?Start(h):-1;LOG("Start=%08x\n",rv);if(rv>=0){started=1;int64_t audio=0;int audio_started=0;unsigned char ap[56]={0};u64(ap,0,56);u64(ap,8,24);u32(ap,0x14,2);u32(ap,0x18,1);u32(ap,0x1c,0xffffffffu);u32(ap,0x28,128000);int ar=OpenAudio?OpenAudio(&audio,ap,0):-1;LOG("OpenAudio=%08x handle=%llx\n",ar,(unsigned long long)audio);if(ar>=0&&audio){ar=Start(audio);audio_started=ar>=0;LOG("StartAudio=%08x\n",ar);}unsigned char*buf=malloc(0x200000);unsigned char*vb=malloc(0x200200);int frames=0,packets=0,errors=0,overruns=0,oversize=0;uint32_t last_read=0;size_t total=0;uint64_t began=mono_us(),last_frame=began,vp0=0,vpn=0,ap0=0,apn=0;uint64_t max_call=0;int running=buf&&vb&&audio_started;if(running&&sent(capture_ack())<0)running=0;while(running){int progress=0;capture_tick(frames,packets,overruns,errors,max_call);if(udp_mode&&!udp_alive()){running=0;continue;}for(int k=0;k<8&&running;k++){static unsigned char abuf[AUDIO_READ_BYTES],adts[ADTS_MAX_FRAME];uint64_t am[2]={16,0};int n=ReadAudio(audio,abuf,sizeof abuf,am,1);if(n>0&&n<=ADTS_MAX_FRAME-7){int size=n+7;adts[0]=0xff;adts[1]=0xf1;adts[2]=0x4c;adts[3]=0x80|(size>>11);adts[4]=size>>3;adts[5]=((size&7)<<5)|0x1f;adts[6]=0xfc;memcpy(adts+7,abuf,n);uint64_t t=am[1]*3/8;if(!packets)ap0=am[1];apn=am[1];if(sent(pes(0x101,0xc0,adts,size,t,t,0))<0)running=0;packets++;progress=1;}else if(n>0){oversize++;progress=1;}else{if((uint32_t)n==0x81950004u)overruns++;else if(n<0&&(uint32_t)n!=0x81950002u){LOG("Audio error=%08x\n",n);errors++;REOPEN_OR_END();}break;}}
unsigned char meta[0x70]={0};u64(meta,0,0x70);uint64_t call=mono_us();int n=Read(h,buf,0x200000,meta,1);call=mono_us()-call;if(call>max_call)max_call=call;if(n>0&&n<=0x200000){uint64_t pt=get64(meta,8),dt=get64(meta,16);if(frames<3){LOG("Video meta %d pts=%llu dts=%llu ageclock=%llu bytes=%d\n",frames,(unsigned long long)pt,(unsigned long long)dt,(unsigned long long)mono_us(),n);}if(!frames)vp0=pt;vpn=pt;size_t vn=delimiter(vb,capture_codec);if(frames%60==0){if(tables()<0)running=0;memcpy(vb+vn,codec,cn);vn+=cn;}memcpy(vb+vn,buf,n);vn+=n;if(sent(pes(0x100,0xe0,vb,vn,pt*3/8,dt*3/8,1))<0)running=0;frames++;total+=n;progress=1;last_frame=mono_us();if(frames==REOPEN_RESET_FRAMES)reopens=0;}else if((uint32_t)n==0x81950004u)overruns++;else if(read_needs_reopen((uint32_t)n)){LOG("Video error=%08x\n",n);errors++;if((uint32_t)n==READ_RAISE_QP)u32(p,0xd4,0x33);REOPEN_OR_END();}else if(n<0&&(uint32_t)n!=0x81950002u&&(uint32_t)n!=last_read){last_read=(uint32_t)n;LOG("Video read=%08x\n",n);}if(!progress){if(running&&mono_us()-last_frame>NO_FRAME_REOPEN_US){LOG("No video for 3 s\n");errors++;REOPEN_OR_END();}usleep(500);}}
LOG("frames=%d audio_packets=%d bytes=%zu elapsed_us=%llu video_first=%llu video_last=%llu audio_first=%llu audio_last=%llu max_read_us=%llu overruns=%d errors=%d audio_oversize=%d\n",frames,packets,total,(unsigned long long)(mono_us()-began),(unsigned long long)vp0,(unsigned long long)vpn,(unsigned long long)ap0,(unsigned long long)apn,(unsigned long long)max_call,overruns,errors,oversize);free(buf);free(vb);if(audio_started)LOG("StopAudio=%08x\n",Stop(audio));if(audio)LOG("CloseAudio=%08x\n",Close(audio));LOG("Stop=%08x\n",Stop(h));}LOG("Close=%08x\n",Close(h));}again=1;}while(reopen);LOG("Resource release=%08x\n",Request(resource_profile,"STOP",0,getpid()));LOG("Resource unregister=%08x\n",Unregister(resource_profile));if(started||capture_resolution==RESOLUTION_1080P)break;refused_by=(uint32_t)rv;usleep(100000);use_resolution(p,supported_resolution(capture_resolution-1,caps));}LOG("Terminate=%08x\n",Term());if(udp_ready){LOG("UDP: datagrams=%llu failed=%llu reports=%llu parity=%u%%\n",(unsigned long long)video_udp.sent,(unsigned long long)video_udp.send_failed,(unsigned long long)video_udp.reports,video_udp.percent);video_udp_close(&video_udp);}udp_ready=udp_mode=0;link_end(&video_link);close(client);client=-1;fclose(logf);return 0;}
/* What a stream leaves behind before the next one, away from home: its connections and its options. */
static void session_reset(void){
 if(video_udp.fd>=0)video_udp_close(&video_udp);
 udp_ready=udp_mode=want_udp=0;
 if(client>=0){link_end(&video_link);close(client);client=-1;}
 capture_fps=60;capture_bitrate=8000000;requested_resolution=capture_resolution=RESOLUTION_1080P;capture_output_mode=0;refused_by=0;capture_codec=CODEC_H264;
 resource_profile=14;options_received=0;notify_viewer=0;viewer_connected=0;
}
/* A stream that ended, or one that could not start, is waited for again; a firmware it does not know, a log it cannot write, or no
   PC within the wait ends the payload. */
static int away_again(int code){return code!=1&&code!=9&&code!=14;}
int main(void){
 /* Sent for play away from home, even the first wait is the away hours: the player may prepare it and leave. */
 secure_start();if(away_on(secure_on,secure_flags))viewer_wait_ms=away_wait_ms(secure_flags);
 int code=stream_main();
 /* Play away from home: after each stream the payload waits for the same PC again, until the away hours pass with no stream or the PC
    ends it. Nothing of the capture is held while it waits: every stream opens and releases it as before. */
 while(away_on(secure_on,secure_flags)&&!away_end&&away_again(code)){
  if(viewer_connected)notice("PlayBridge stopped streaming to your PC. It waits for it to come back.");
  session_reset();viewer_wait_ms=away_wait_ms(secure_flags);code=stream_main();
 }
 control_stop();if(viewer_connected)notice(code?"PlayBridge stopped: the capture could not start.":"PlayBridge stopped streaming to your PC.");return code;
}
