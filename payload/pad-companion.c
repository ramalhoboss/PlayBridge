/* The controller companion: a payload of its own, sent beside the video payload. It runs in its own process on UDP 9078 and never opens a
   capture or the video and control ports, so if a console call here never returns, the stream and the control port carry on.
   The controller is made straight on /dev/hid (see pad-rules.h): no libScePad and no scePadInit, whose wait on the console's Mbus service
   is what stopped the first attempt. */
#include <ps5/kernel.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <fcntl.h>
#include <dirent.h>
#include <time.h>
#include <poll.h>
#include <pthread.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/param.h>
#include <sys/sysctl.h>
#include <sys/user.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include "pad-rules.h"
typedef int(*load_fn)(const char*,size_t,const void*,uint32_t,void*,int*);
static FILE*logf;
#define LOG(...) do{if(logf){fprintf(logf,__VA_ARGS__);fflush(logf);}}while(0)
/* The controller this companion made. A companion that is killed never removes it, so the next one removes what this file names. */
#define HANDLES "/data/playbridge-pad.handles"
static uint64_t now_us(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000+(uint64_t)t.tv_nsec/1000;}
static uint32_t module(load_fn load,const char*name){
 uint32_t h=0;if(!kernel_dynlib_handle(-1,name,&h)&&h)return h;
 const char*roots[]={"/system/common/lib/","/system/priv/lib/","/system_ex/common_ex/lib/",0};
 for(int i=0;load&&roots[i];i++){char p[256];snprintf(p,sizeof p,"%s%s",roots[i],name);int result=0;int rv=load(p,0,0,0,0,&result);LOG("load %s rv=%x result=%x\n",p,rv,result);if(!kernel_dynlib_handle(-1,name,&h)&&h)return h;}
 return 0;
}
static void*symbol(uint32_t handle,const char*name){void*p=handle?(void*)kernel_dynlib_dlsym(-1,handle,name):0;LOG("%s=%p\n",name,p);return p;}
/* By NID, for calls the SDK has no stub for: the NID is worked out from the name (tests/test_pad_companion.py checks each one). An
   address outside user space is taken as not found. */
static void*by_nid(uint32_t handle,const char*nid,const char*name){
 intptr_t p=handle?kernel_dynlib_resolve(-1,handle,nid):0;if(p<=0x10000||(uint64_t)p>=0x0000800000000000ull)p=0;LOG("%s=%p\n",name,(void*)p);return (void*)p;
}
static struct{int(*user_init)(void*);int(*foreground)(int*);}sce;
static struct{int32_t(*init)(uint64_t,uint64_t);int32_t(*bind)(uint64_t,int32_t);int32_t(*info)(uint64_t,void*,uint32_t);}mbus;
enum{MBUS_STARTING=0,MBUS_READY=1,MBUS_FAILED=2};static int mbus_state=MBUS_STARTING;
static int pad_socket=-1,hid=-1,start_state=PAD_STARTING;static int32_t start_error;static uint64_t began;static uint32_t user_id;
/* The error first, so whoever sees the state also sees its error. */
static void started(int state,int32_t error){__atomic_store_n(&start_error,error,__ATOMIC_RELEASE);__atomic_store_n(&start_state,state,__ATOMIC_RELEASE);}
static int progress(int32_t*error){int state=__atomic_load_n(&start_state,__ATOMIC_ACQUIRE);*error=__atomic_load_n(&start_error,__ATOMIC_ACQUIRE);return state;}
static void step(int n){__atomic_store_n(&start_error,PAD_STEP(n),__ATOMIC_RELEASE);LOG("step %d at %llu ms\n",n,(unsigned long long)(now_us()-began)/1000);}
/* The first user folder in /user/home (8 hex digits, not 0), for when the console names no user in front. */
static uint32_t home_user(void){
 DIR*d=opendir("/user/home");if(!d)return 0;struct dirent*e;uint32_t found=0;
 while(!found&&(e=readdir(d))){if(strlen(e->d_name)!=8)continue;char*end=0;unsigned long v=strtoul(e->d_name,&end,16);if(end&&!*end&&v)found=(uint32_t)v;}
 closedir(d);return found;
}
/* The controllers made so far, written down after every change so the next companion can remove what a killed one left. */
static int live[PAD_SLOTS]={-1,-1,-1,-1};
static void write_handles(void){
 FILE*f=fopen(HANDLES,"w");if(!f)return;
 for(int i=0;i<PAD_SLOTS;i++)if(live[i]>=0)fprintf(f,"%d\n",live[i]);
 fclose(f);
}
static int32_t delete_controller(int handle){struct pad_delete_request r;memset(&r,0,sizeof r);r.op=PAD_OP_DELETE;r.handle=(uint32_t)handle;return ioctl(hid,PAD_HID_DELETE,&r)==0?0:PAD_ERRNO(errno);}
static void remove_leftovers(void){
 FILE*f=fopen(HANDLES,"r");if(!f)return;int handle;
 while(fscanf(f,"%d",&handle)==1)LOG("leftover controller %d removed: %08x\n",handle,(uint32_t)delete_controller(handle));
 fclose(f);unlink(HANDLES);
}
static int32_t add_controller(int*handle){
 unsigned char description[PAD_BLOCK_SIZE];pad_description(description,user_id);int made=-1;uint64_t at=now_us();
 struct pad_add_request r;memset(&r,0,sizeof r);r.op=PAD_OP_ADD;r.description=(uint64_t)(uintptr_t)description;r.handle=(uint64_t)(uintptr_t)&made;
 int rv=ioctl(hid,PAD_HID_ADD,&r);int e=rv?errno:0;
 LOG("add controller for user %08x rv=%d errno=%d handle=%d after %llu ms\n",user_id,rv,e,made,(unsigned long long)(now_us()-at)/1000);
 if(rv)return PAD_ERRNO(e);
 *handle=made;
 if(made>=0)for(int i=0;i<PAD_SLOTS;i++)if(live[i]<0){live[i]=made;break;}
 write_handles();return 0;
}
static int32_t insert_state(int handle,const unsigned char*block){
 struct pad_insert_request r;memset(&r,0,sizeof r);r.handle=(uint32_t)handle;r.state=(uint64_t)(uintptr_t)block;
 return ioctl(hid,PAD_HID_INSERT,&r)==0?0:PAD_ERRNO(errno);
}
static int32_t remove_controller(int handle){
 int32_t rv=delete_controller(handle);LOG("controller %d removed: %08x\n",handle,(uint32_t)rv);
 for(int i=0;i<PAD_SLOTS;i++)if(live[i]==handle)live[i]=-1;
 write_handles();return rv;
}
/* sceMbusInit runs on a thread of its own and is waited for a second at most: ps5upload saw it freeze its main process, and if it never
   comes back here, the controllers still play and the PS5 asks who is using each one. */
static void*start_mbus(void*unused){(void)unused;
 int32_t rv=mbus.init(0,0);LOG("sceMbusInit=%08x\n",(uint32_t)rv);
 __atomic_store_n(&mbus_state,rv==0?MBUS_READY:MBUS_FAILED,__ATOMIC_RELEASE);return 0;
}
static void start_seats(void){
 if(!mbus.init||!mbus.bind||!mbus.info){LOG("Mbus calls not found: the PS5 will ask who is using each controller\n");__atomic_store_n(&mbus_state,MBUS_FAILED,__ATOMIC_RELEASE);return;}
 pthread_t thread;
 if(pthread_create(&thread,0,start_mbus,0)){LOG("Mbus thread not created errno=%d\n",errno);__atomic_store_n(&mbus_state,MBUS_FAILED,__ATOMIC_RELEASE);return;}
 pthread_detach(thread);
 for(int i=0;i<200&&__atomic_load_n(&mbus_state,__ATOMIC_ACQUIRE)==MBUS_STARTING;i++)usleep(5000);
 if(__atomic_load_n(&mbus_state,__ATOMIC_ACQUIRE)==MBUS_STARTING)LOG("sceMbusInit has not come back after 1 s: controllers start without a seat\n");
}
static void pause_ms(void){usleep(1000);}
static int32_t seat_controller(int handle){
 if(__atomic_load_n(&mbus_state,__ATOMIC_ACQUIRE)!=MBUS_READY){LOG("controller %d not seated: Mbus is not ready\n",handle);return PAD_NO_SEAT;}
 struct pad_mbus m={mbus.bind,mbus.info,pause_ms};uint32_t owner=0;int tries=0;uint64_t at=now_us();
 int32_t rv=pad_seat(&m,handle,user_id,&owner,&tries);
 LOG("controller %d seated with user %08x: %08x after %d tries in %llu us, owner %08x\n",handle,user_id,(uint32_t)rv,tries,(unsigned long long)(now_us()-at),owner);
 return rv;
}
/* The calls that may wait on console services, on their own thread: the loop keeps answering the PC while these run, with the step under
   way, and gives up on them after a few seconds. Each step's time goes in the log. Controllers are added later, one per sender. */
static void*start_pad(void*unused){(void)unused;
 step(PAD_STEP_USER);if(sce.user_init)LOG("sceUserServiceInitialize=%08x\n",sce.user_init(0));
 step(PAD_STEP_FOREGROUND);uint32_t user=0;int rv=sce.foreground?sce.foreground((int*)&user):-1;LOG("foreground user=%08x rv=%08x\n",user,rv);
 if(rv<0||!user||user==0xffffffffu){user=home_user();LOG("first user in /user/home=%08x\n",user);}
 if(!user){started(PAD_FAILED,PAD_NO_USER);return 0;}
 user_id=user;
 step(PAD_STEP_OPEN);int fd=open("/dev/hid",O_RDONLY);
 if(fd<0){int e=errno;LOG("open /dev/hid errno=%d\n",e);started(PAD_FAILED,PAD_ERRNO(e));return 0;}
 hid=fd;
 step(PAD_STEP_LEFTOVERS);remove_leftovers();
 step(PAD_STEP_SEAT);start_seats();
 started(PAD_READY,0);return 0;
}
static uint64_t sender_key(const struct sockaddr_in*a){return (uint64_t)ntohl(a->sin_addr.s_addr)<<16|ntohs(a->sin_port);}
static int receive(unsigned char*w,size_t cap,int timeout_ms,uint64_t*sender){
 struct pollfd p={pad_socket,POLLIN,0};int ready=poll(&p,1,timeout_ms);
 if(ready==0)return 0;
 if(ready<0)return errno==EINTR?0:-1;
 struct sockaddr_in from;socklen_t size=sizeof from;ssize_t n=recvfrom(pad_socket,w,cap,0,(struct sockaddr*)&from,&size);
 if(n<0)return errno==EINTR||errno==EAGAIN?0:-1;
 *sender=sender_key(&from);
 return (int)n;
}
static void answer(uint64_t sender,const unsigned char*w,size_t n){
 struct sockaddr_in to={0};to.sin_len=sizeof to;to.sin_family=AF_INET;to.sin_addr.s_addr=htonl((uint32_t)(sender>>16));to.sin_port=htons((uint16_t)sender);
 sendto(pad_socket,w,n,MSG_DONTWAIT,(struct sockaddr*)&to,sizeof to);
}
/* No SO_REUSEADDR: a second copy must find the port taken and leave, so the one already running keeps the controller. */
static int open_socket(void){
 int s=socket(AF_INET,SOCK_DGRAM,0);if(s<0)return -1;
 struct sockaddr_in a={0};a.sin_len=sizeof a;a.sin_family=AF_INET;a.sin_port=htons(PAD_PORT);a.sin_addr.s_addr=htonl(INADDR_ANY);
 if(bind(s,(struct sockaddr*)&a,sizeof a)<0){int e=errno;close(s);errno=e;return -1;}
 return s;
}
/* Whether the copy holding the port answers. A working one always does, at once, whatever its state. */
static int running_copy_answers(void){
 int s=socket(AF_INET,SOCK_DGRAM,0);if(s<0)return 1;
 struct sockaddr_in a={0};a.sin_len=sizeof a;a.sin_family=AF_INET;a.sin_port=htons(PAD_PORT);a.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
 unsigned char probe[PAD_PROBE_SIZE]={'P','B','H','1',0,0,0,0},reply[64];int answered=0;
 for(int i=0;i<3&&!answered;i++){
  sendto(s,probe,sizeof probe,0,(struct sockaddr*)&a,sizeof a);
  struct pollfd p={s,POLLIN,0};
  if(poll(&p,1,400)>0){ssize_t n=recv(s,reply,sizeof reply,0);answered=n==PAD_STATUS_SIZE&&reply[0]=='P'&&reply[1]=='B'&&reply[2]=='S';}
 }
 close(s);return answered;
}
/* The pid an earlier copy wrote on its log's first line, if that log has no end line: a copy that may still be running. 0 otherwise. */
static pid_t unended_copy(const char*path){
 FILE*f=fopen(path,"r");if(!f)return 0;
 char line[256];pid_t pid=0;
 if(fgets(line,sizeof line,f)){char*at=strstr(line,"pid=");if(at&&strstr(line,"PlayBridge controller"))pid=(pid_t)atoi(at+4);}
 while(pid>0&&fgets(line,sizeof line,f))if(!strncmp(line,"end=",4))pid=0;
 fclose(f);return pid>1&&pid!=getpid()?pid:0;
}
/* That pid, if it is still alive and a payload, so that it may be the one holding the port without answering. 0 otherwise. The PS5's
   process record is larger than the SDK's (a buffer of the SDK's size came back ENOMEM), so it is read into a larger one; the fields read
   here are the first ones, where both agree, and the pid read back confirms it. */
static pid_t silent_copy(pid_t pid){
 if(pid<=0)return 0;
 static unsigned char record[0x2000];size_t size=sizeof record;int mib[4]={CTL_KERN,KERN_PROC,KERN_PROC_PID,pid};
 if(sysctl(mib,4,record,&size,0,0)<0){LOG("earlier copy pid=%d: no such process (errno=%d)\n",(int)pid,errno);return 0;}
 struct kinfo_proc*info=(struct kinfo_proc*)record;
 if(size<sizeof*info||info->ki_pid!=pid){LOG("earlier copy pid=%d: record of %zu bytes names pid %d\n",(int)pid,size,size>=sizeof*info?(int)info->ki_pid:-1);return 0;}
 char name[COMMLEN+1];memcpy(name,info->ki_comm,COMMLEN);name[COMMLEN]=0;
 LOG("earlier copy pid=%d is %s (record %zu bytes)\n",(int)pid,name,size);
 return strcmp(name,"payload.elf")?0:pid;
}
int main(void){
 began=now_us();
 /* Read before the logs move on: the last two copies, in case one of them holds the port without answering. */
 pid_t earlier[2]={unended_copy("/data/playbridge-pad.txt"),unended_copy("/data/playbridge-pad.old.txt")};
 /* The previous run's log is kept, because it is the only record of a run that did not end well. */
 rename("/data/playbridge-pad.txt","/data/playbridge-pad.old.txt");
 logf=fopen("/data/playbridge-pad.txt","w");
 LOG("PlayBridge controller v2 (/dev/hid) pid=%d fw=%08x\n",getpid(),kernel_get_fw_version());
 if(kernel_get_fw_version()!=0x13600007u){LOG("unsupported firmware\nend=firmware\n");if(logf)fclose(logf);return 9;}
 pad_socket=open_socket();
 /* The port taken: a copy that answers keeps it and its controllers. One that never answers is a copy that stopped (a crash on the PS5
    freezes the process and it keeps the port), so it is ended and the port taken over. */
 if(pad_socket<0){
  LOG("UDP %d not available errno=%d\n",PAD_PORT,errno);
  if(running_copy_answers()){LOG("another copy answers: it keeps the controllers\nend=taken\n");if(logf)fclose(logf);return 14;}
  for(int k=0;k<2&&pad_socket<0;k++){
   pid_t old=silent_copy(earlier[k]);if(old<=0)continue;
   int rv=kill(old,SIGKILL);LOG("the copy holding the port does not answer: ended pid=%d rv=%d errno=%d\n",(int)old,rv,rv?errno:0);
   for(int i=0;i<30&&pad_socket<0;i++){usleep(100000);pad_socket=open_socket();}
  }
  if(pad_socket<0){LOG("the port stays taken errno=%d\nend=taken\n",errno);if(logf)fclose(logf);return 14;}
  LOG("port taken over\n");
 }
 /* The SDK's kernel calls share one set of descriptors and are not safe across threads, so every symbol is looked up here, before the
    start-up thread exists, and that thread only ever calls the results. */
 uint32_t kh=0;const char*ks[]={"libkernel_web.sprx","libkernel.sprx","libkernel_sys.sprx",0};
 for(int i=0;ks[i];i++)if(!kernel_dynlib_handle(-1,ks[i],&kh)&&kh)break;
 load_fn load=kh?(load_fn)kernel_dynlib_resolve(-1,kh,"wzvqT4UqKX8"):0;
 /* libSceIpmi first: the console's loader does not set up a library's IPC for it, and without it sceUserServiceInitialize crashed the
    first run on the PS5 (the video payload loads it first and the same call works there). The SDK maintainers give the same order. */
 module(load,"libSceIpmi.sprx");
 uint32_t user=module(load,"libSceUserService.sprx");
 sce.user_init=symbol(user,"sceUserServiceInitialize");sce.foreground=symbol(user,"sceUserServiceGetForegroundUser");
 uint32_t bus=module(load,"libSceMbus.sprx");
 mbus.init=by_nid(bus,"wRPXMGtkOq0","sceMbusInit");mbus.bind=by_nid(bus,"Cpo6sQmnZgU","sceMbusBindDeviceWithUserId");
 mbus.info=by_nid(bus,"RsKVKhSWt28","sceMbusGetDeviceInfo_");
 pthread_t thread;
 if(pthread_create(&thread,0,start_pad,0)==0)pthread_detach(thread);
 else{LOG("start-up thread not created errno=%d\n",errno);started(PAD_FAILED,PAD_MISSING);}
 struct pad_calls calls={receive,answer,now_us,progress,add_controller,insert_state,remove_controller,seat_controller};struct pad_report report={0};
 /* The loop removes every controller it made before it returns. */
 int end=pad_run(&calls,&report);
 LOG("end=%d packets=%u added=%u removed=%u refused=%u seated=%u seat_failed=%u first_seat_error=%08x inserted=%u neutral=%u answers=%u ignored=%u insert_failed=%u first_insert_error=%08x\n",end,report.packets,report.added,report.removed,report.refused,report.seated,report.seat_failed,report.first_seat_error,report.inserted,report.neutral,report.answers,report.ignored,report.insert_failed,report.first_insert_error);
 close(pad_socket);pad_socket=-1;
 int32_t error=0;int state=progress(&error);
 if(state==PAD_READY){int left=0;for(int i=0;i<PAD_SLOTS;i++)left+=live[i]>=0;if(!left)unlink(HANDLES);}
 else LOG("state=%d error=%08x%s\n",state,error,state==PAD_STARTING?": start-up still has not returned, leaving without it":"");
 /* The log stays open: a start-up thread that comes back now may still write to it, and every line is already flushed. */
 _exit(end==PAD_END_IDLE?0:end);
}
