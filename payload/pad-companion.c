/* The controller companion: a payload of its own, sent beside the video payload. It runs in its own process on UDP 9078 and never opens a
   capture or the video and control ports, so if a console call here never returns, the stream and the control port carry on. */
#include <ps5/kernel.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <time.h>
#include <poll.h>
#include <pthread.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include "pad-rules.h"
typedef int(*load_fn)(const char*,size_t,const void*,uint32_t,void*,int*);
static FILE*logf;
#define LOG(...) do{if(logf){fprintf(logf,__VA_ARGS__);fflush(logf);}}while(0)
static uint64_t now_us(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000+(uint64_t)t.tv_nsec/1000;}
static uint32_t module(load_fn load,const char*name){
 uint32_t h=0;if(!kernel_dynlib_handle(-1,name,&h)&&h)return h;
 const char*roots[]={"/system/common/lib/","/system/priv/lib/","/system_ex/common_ex/lib/",0};
 for(int i=0;load&&roots[i];i++){char p[256];snprintf(p,sizeof p,"%s%s",roots[i],name);int result=0;int rv=load(p,0,0,0,0,&result);LOG("load %s rv=%x result=%x\n",p,rv,result);if(!kernel_dynlib_handle(-1,name,&h)&&h)return h;}
 return 0;
}
static void*symbol(uint32_t handle,const char*name){void*p=handle?(void*)kernel_dynlib_dlsym(-1,handle,name):0;LOG("%s=%p\n",name,p);return p;}
static struct{int(*user_init)(void*);int(*foreground)(int*);int(*pad_init)(void);int(*pad_add)(void*,int*);int(*pad_insert)(int,void*);int(*pad_delete)(int);}sce;
static int pad_socket=-1,pad_device=-1,start_state=PAD_STARTING;static int32_t start_error;
static struct sockaddr_in sender;static int has_sender;
/* The error first, so whoever sees the state also sees its error. */
static void started(int state,int32_t error){__atomic_store_n(&start_error,error,__ATOMIC_RELEASE);__atomic_store_n(&start_state,state,__ATOMIC_RELEASE);}
static int progress(int32_t*error){int state=__atomic_load_n(&start_state,__ATOMIC_ACQUIRE);*error=__atomic_load_n(&start_error,__ATOMIC_ACQUIRE);return state;}
#define VIRTUAL_PAD_TYPE 1
/* The calls that may wait on console services, on their own thread. scePadInit never returned inside the video payload on firmware 13.60,
   so the loop keeps answering the PC while these run and gives up on them after a few seconds. */
static void*start_pad(void*unused){(void)unused;
 if(!sce.pad_init||!sce.pad_add||!sce.pad_insert){started(PAD_FAILED,PAD_MISSING);return 0;}
 /* Each call's time goes in the log: scePadInit gives up by itself after about 5 s when the console's Mbus service refuses this
    process, and does not come back at all when the connection waits on it. */
 uint64_t at=now_us();
 if(sce.user_init)LOG("sceUserServiceInitialize=%08x\n",sce.user_init(0));
 int user=-1,rv=sce.foreground?sce.foreground(&user):-1;LOG("foreground user=%d rv=%08x\n",user,rv);
 if(rv<0||user<0){started(PAD_FAILED,PAD_NO_USER);return 0;}
 LOG("scePadInit... (%llu ms in)\n",(unsigned long long)(now_us()-at)/1000);at=now_us();rv=sce.pad_init();LOG("scePadInit=%08x after %llu ms\n",rv,(unsigned long long)(now_us()-at)/1000);
 if(rv<0){started(PAD_FAILED,rv);return 0;}
 struct{int user;unsigned char type;unsigned char reserved[123];}request={user,VIRTUAL_PAD_TYPE,{0}};int device=-1;
 at=now_us();rv=sce.pad_add(&request,&device);LOG("scePadVirtualDeviceAddDevice user=%d type=%d rv=%08x device=%d after %llu ms\n",user,VIRTUAL_PAD_TYPE,rv,device,(unsigned long long)(now_us()-at)/1000);
 if(rv<0){started(PAD_FAILED,rv);return 0;}
 if(device<0){started(PAD_FAILED,PAD_NO_DEVICE);return 0;}
 __atomic_store_n(&pad_device,device,__ATOMIC_RELEASE);started(PAD_READY,0);return 0;
}
static int receive(unsigned char*w,size_t cap,int timeout_ms){
 struct pollfd p={pad_socket,POLLIN,0};int ready=poll(&p,1,timeout_ms);
 if(ready==0)return 0;
 if(ready<0)return errno==EINTR?0:-1;
 struct sockaddr_in from;socklen_t size=sizeof from;ssize_t n=recvfrom(pad_socket,w,cap,0,(struct sockaddr*)&from,&size);
 if(n<0)return errno==EINTR||errno==EAGAIN?0:-1;
 if(n>0){sender=from;has_sender=1;}
 return (int)n;
}
static void answer(const unsigned char*w,size_t n){if(has_sender)sendto(pad_socket,w,n,MSG_DONTWAIT,(struct sockaddr*)&sender,sizeof sender);}
static int insert(const unsigned char*record){return sce.pad_insert(__atomic_load_n(&pad_device,__ATOMIC_ACQUIRE),(void*)record);}
/* No SO_REUSEADDR: a second copy must find the port taken and leave, so the one already running keeps the controller. */
static int open_socket(void){
 int s=socket(AF_INET,SOCK_DGRAM,0);if(s<0)return -1;
 struct sockaddr_in a={0};a.sin_len=sizeof a;a.sin_family=AF_INET;a.sin_port=htons(PAD_PORT);a.sin_addr.s_addr=htonl(INADDR_ANY);
 if(bind(s,(struct sockaddr*)&a,sizeof a)<0){int e=errno;close(s);errno=e;return -1;}
 return s;
}
int main(void){
 /* The previous run's log is kept, because it is the only record of a run that did not end well. */
 rename("/data/playbridge-pad.txt","/data/playbridge-pad.old.txt");
 logf=fopen("/data/playbridge-pad.txt","w");
 LOG("PlayBridge controller v1 pid=%d fw=%08x\n",getpid(),kernel_get_fw_version());
 if(kernel_get_fw_version()!=0x13600007u){LOG("unsupported firmware\n");if(logf)fclose(logf);return 9;}
 pad_socket=open_socket();
 if(pad_socket<0){LOG("UDP %d not available errno=%d: another copy is already running\n",PAD_PORT,errno);if(logf)fclose(logf);return 14;}
 /* The SDK's kernel calls share one set of descriptors and are not safe across threads, so every symbol is looked up here, before the
    start-up thread exists, and that thread only ever calls the results. */
 uint32_t kh=0;const char*ks[]={"libkernel_web.sprx","libkernel.sprx","libkernel_sys.sprx",0};
 for(int i=0;ks[i];i++)if(!kernel_dynlib_handle(-1,ks[i],&kh)&&kh)break;
 load_fn load=kh?(load_fn)kernel_dynlib_resolve(-1,kh,"wzvqT4UqKX8"):0;
 uint32_t user=module(load,"libSceUserService.sprx"),pad=module(load,"libScePad.sprx"),mbus=0;
 /* Only noted, not loaded: the console's own Remote Play process has it beside libScePad, and this one may not. */
 kernel_dynlib_handle(-1,"libSceMbus.sprx",&mbus);LOG("libSceMbus handle=%x\n",mbus);
 sce.user_init=symbol(user,"sceUserServiceInitialize");sce.foreground=symbol(user,"sceUserServiceGetForegroundUser");
 sce.pad_init=symbol(pad,"scePadInit");sce.pad_add=symbol(pad,"scePadVirtualDeviceAddDevice");sce.pad_insert=symbol(pad,"scePadVirtualDeviceInsertData");sce.pad_delete=symbol(pad,"scePadVirtualDeviceDeleteDevice");
 pthread_t thread;
 if(pthread_create(&thread,0,start_pad,0)==0)pthread_detach(thread);
 else{LOG("start-up thread not created errno=%d\n",errno);started(PAD_FAILED,PAD_MISSING);}
 struct pad_calls calls={receive,answer,now_us,progress,insert};struct pad_report report={0};
 int end=pad_run(&calls,&report);
 LOG("end=%d packets=%u inserted=%u neutral=%u answers=%u ignored=%u insert_failed=%u first_insert_error=%08x\n",end,report.packets,report.inserted,report.neutral,report.answers,report.ignored,report.insert_failed,report.first_insert_error);
 /* The port goes back first, even if the start-up thread never returns. */
 close(pad_socket);pad_socket=-1;
 int32_t error=0;int state=progress(&error);
 if(state==PAD_READY){
  static const unsigned char centred[6]={0x80,0x80,0x80,0x80,0,0};unsigned char record[PAD_DATA_SIZE];fill_pad_data(record,0,centred,now_us());insert(record);
  if(sce.pad_delete)LOG("scePadVirtualDeviceDeleteDevice=%08x\n",sce.pad_delete(__atomic_load_n(&pad_device,__ATOMIC_ACQUIRE)));
 }else LOG("state=%d error=%08x%s\n",state,error,state==PAD_STARTING?": start-up still has not returned, leaving without it":"");
 /* The log stays open: a start-up thread that comes back now may still write to it, and every line is already flushed. */
 _exit(end==PAD_END_IDLE?0:end);
}
