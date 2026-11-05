/* Console side of the game library, status, power and PC controller. Lives only as long as the capture session. */
#include <pthread.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <dirent.h>
#include "control-rules.h"
int sceKernelGetCpuTemperature(int*);
int sceKernelGetSocSensorTemperature(int,int*);
int sceKernelGetSocPowerConsumption(int*);
long sceKernelGetCpuFrequency(void);
static struct{
 int(*user_init)(void*);int(*foreground)(int*);int(*lnc_init)(void);
 int(*launch)(const char*,char**,void*);int(*big_app)(void);int(*title_of)(int,char*);int(*kill)(int);
 int(*front)(void*);int(*rest)(int);int(*off)(int);int(*reboot)(int);
 int(*pad_init)(void);int(*pad_add)(void*,int*);int(*pad_insert)(int,void*);int(*pad_delete)(int);
}sce;
static FILE*control_log;
static int control_listener=-1,pad_socket=-1,pad_device=-1;
#define CLOG(...) do{if(control_log){fprintf(control_log,__VA_ARGS__);fflush(control_log);}}while(0)
static void*symbol(uint32_t handle,const char*name){void*p=handle?(void*)kernel_dynlib_dlsym(-1,handle,name):0;CLOG("%s=%p\n",name,p);return p;}
static int control_write(int fd,const void*data,size_t n){const unsigned char*p=data;while(n){ssize_t w=send(fd,p,n,0);if(w<=0)return -1;p+=w;n-=(size_t)w;}return 0;}
static int control_read(int fd,void*data,size_t n){unsigned char*p=data;while(n){ssize_t r=recv(fd,p,n,0);if(r<=0)return -1;p+=r;n-=(size_t)r;}return 0;}
static int control_header(int fd,int result,uint32_t n){unsigned char h[12];memcpy(h,"PBR1",4);memcpy(h+4,&result,4);memcpy(h+8,&n,4);return control_write(fd,h,12);}
static int control_reply(int fd,int result,const void*body,uint32_t n){return control_header(fd,result,n)||(n&&control_write(fd,body,n))?-1:0;}
static int foreground_user(void){int user=-1;if(sce.foreground&&sce.foreground(&user)<0)user=-1;return user;}
static void json_safe_title(char*title){title[15]=0;for(int i=0;title[i];i++)if(title[i]<' '||title[i]=='"'||title[i]=='\\')title[i]='?';}
static int control_status(int fd){
 /* Room for more than an int each: with no game open, the bytes next to these readings came back changed. */
 int cpu[4]={-1},soc[4]={-1},power[4]={-1},app=-1;char title[16]={0};
 sceKernelGetCpuTemperature(cpu);sceKernelGetSocSensorTemperature(0,soc);sceKernelGetSocPowerConsumption(power);
 if(sce.big_app){app=sce.big_app();if(app>0&&sce.title_of&&sce.title_of(app,title)<0)title[0]=0;}
 /* The app on the screen, which is the console's menu while the PS button has it over a game. The title id sits at +16 and the full size of this answer is not known, so there is plenty of room. */
 static unsigned char focus[512];char front[16]={0};if(sce.front&&sce.front(focus)==0)memcpy(front,focus+16,15);
 json_safe_title(title);json_safe_title(front);
 char body[256];int n=snprintf(body,sizeof body,"{\"cpu_c\":%d,\"soc_c\":%d,\"power_mw\":%d,\"cpu_mhz\":%ld,\"user\":%d,\"app\":%d,\"title\":\"%s\",\"front\":\"%s\",\"pad\":%d}",cpu[0],soc[0],power[0],sceKernelGetCpuFrequency()/1000000,foreground_user(),app,title,front,pad_device>=0);
 return control_reply(fd,0,body,(uint32_t)n);
}
static int control_file(int fd,const char*path,uint32_t length){
 if(!allowed_file(path,length))return control_reply(fd,EACCES,0,0);
 int file=open(path,O_RDONLY);if(file<0)return control_reply(fd,errno,0,0);
 /* Game files stay small. A clip can be long, but the reply's size field holds at most 4 GB. */
 struct stat info;int failed=fstat(file,&info)<0||info.st_size>(capture_file(path,length)?0xfffffffeLL:0x10000000LL);
 if(failed){close(file);return control_reply(fd,EFBIG,0,0);}
 uint32_t left=(uint32_t)info.st_size;if(control_header(fd,0,left)<0){close(file);return -1;}
 static unsigned char chunk[0x10000];
 while(left){ssize_t r=read(file,chunk,left<sizeof chunk?left:sizeof chunk);if(r<=0||control_write(fd,chunk,(size_t)r)<0){close(file);return -1;}left-=(uint32_t)r;
  /* About 4 MB/s, so a refresh does not take the Wi-Fi away from the video. */
  usleep(16000);}
 close(file);return 0;
}
/* One line for each entry of a capture folder: d or f, size, change time, name. Names that would break a line are left out. */
static int control_list(int fd,const char*path,uint32_t length){
 if(!allowed_folder(path,length))return control_reply(fd,EACCES,0,0);
 DIR*dir=opendir(path);if(!dir)return control_reply(fd,errno,0,0);
 static char out[0x10000];size_t used=0;struct dirent*entry;char full[600];
 while((entry=readdir(dir))!=0){
  const char*name=entry->d_name;if(name[0]=='.')continue;
  int odd=0;for(int i=0;name[i];i++)if((unsigned char)name[i]<0x20||name[i]==127)odd=1;
  if(odd)continue;
  int n=snprintf(full,sizeof full,"%s/%s",path,name);if(n<0||n>=(int)sizeof full)continue;
  struct stat info;if(stat(full,&info)<0)continue;
  int w=snprintf(out+used,sizeof out-used,"%c\t%lld\t%lld\t%s\n",S_ISDIR(info.st_mode)?'d':'f',(long long)info.st_size,(long long)info.st_mtime,name);
  if(w<0||(size_t)w>=sizeof out-used)break;
  used+=(size_t)w;
 }
 closedir(dir);return control_reply(fd,0,out,(uint32_t)used);
}
static int control_launch(const char*title,uint32_t length){
 if(!valid_title(title,length))return EINVAL;
 if(!sce.launch)return ENOSYS;
 struct{uint32_t size,user,options,reserved;uint64_t crash_report;}param={sizeof param,(uint32_t)foreground_user(),0,0,0};
 int rv=sce.launch(title,0,&param);CLOG("launch %s user=%d rv=%08x\n",title,(int)param.user,rv);
 /* On success the console answers with the new app's id, not 0. */
 return rv>0?0:rv;
}
static int control_close(void){
 int app=sce.big_app?sce.big_app():-1;CLOG("close app=%08x\n",app);
 if(app<=0)return ENOENT;
 if(!sce.kill)return ENOSYS;
 int rv=sce.kill(app);CLOG("kill rv=%08x\n",rv);return rv;
}
static void control_session(int fd){
 struct timeval limit={5,0};setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&limit,sizeof limit);int nd=1;setsockopt(fd,IPPROTO_TCP,TCP_NODELAY,&nd,sizeof nd);
 for(;;){
  unsigned char h[12];char body[CONTROL_BODY_MAX+1];uint32_t command,length;
  if(control_read(fd,h,12)<0||memcmp(h,"PBC1",4))return;
  memcpy(&command,h+4,4);memcpy(&length,h+8,4);if(length>CONTROL_BODY_MAX||control_read(fd,body,length)<0)return;
  body[length]=0;int failed=0;
  if(command==CONTROL_STATUS)failed=control_status(fd);
  else if(command==CONTROL_FILE)failed=control_file(fd,body,length);
  else if(command==CONTROL_LIST)failed=control_list(fd,body,length);
  else if(command==CONTROL_LAUNCH)failed=control_reply(fd,control_launch(body,length),0,0);
  else if(command==CONTROL_CLOSE)failed=control_reply(fd,control_close(),0,0);
  /* These three answer first: the console may be gone before they return. */
  else if(command==CONTROL_REST){failed=control_reply(fd,sce.rest?0:ENOSYS,0,0);usleep(200000);if(sce.rest)CLOG("standby rv=%08x\n",sce.rest(0));}
  else if(command==CONTROL_POWER_OFF){failed=control_reply(fd,sce.off?0:ENOSYS,0,0);usleep(200000);if(sce.off)CLOG("turn off rv=%08x\n",sce.off(0));}
  else if(command==CONTROL_REBOOT){failed=control_reply(fd,sce.reboot?0:ENOSYS,0,0);usleep(200000);if(sce.reboot)CLOG("reboot rv=%08x\n",sce.reboot(0));}
  else failed=control_reply(fd,EINVAL,0,0);
  if(failed)return;
 }
}
#define VIRTUAL_PAD_TYPE 1
/* Off for now: on firmware 13.60 scePadInit never returned inside this process, and the status calls stopped answering with it. */
#define VIRTUAL_PAD_ENABLED 0
static int pad_open(void){
 if(pad_device>=0)return 0;
 if(!sce.pad_add||!sce.pad_insert)return -1;
 static int pad_ready;if(!pad_ready&&sce.pad_init){int rv=sce.pad_init();CLOG("scePadInit=%08x\n",rv);pad_ready=1;}
 struct{int user;unsigned char type;unsigned char reserved[123];}request={foreground_user(),VIRTUAL_PAD_TYPE,{0}};int device=-1;
 int rv=sce.pad_add(&request,&device);CLOG("virtual pad user=%d add=%08x device=%08x\n",request.user,rv,device);
 if(rv<0||device<0)return -1;
 pad_device=device;return 0;
}
static void*pad_thread(void*unused){(void)unused;
 static const unsigned char centred[6]={0x80,0x80,0x80,0x80,0,0};
 unsigned char wire[64],state[PAD_DATA_SIZE],sticks[6];uint32_t sequence,buttons=0,last=0;int seen=0,held=0;
 for(;;){
  struct pollfd p={pad_socket,POLLIN,0};int ready=poll(&p,1,250);
  /* The PC sends all the time while a controller is in use, so silence means it is gone: no button may stay held. */
  if(ready==0){if(held&&pad_device>=0){fill_pad_data(state,0,centred,mono_us());sce.pad_insert(pad_device,state);held=0;}continue;}
  if(ready<0){if(errno==EINTR)continue;return 0;}
  ssize_t n=recv(pad_socket,wire,sizeof wire,0);if(n<0)continue;
  if(!read_pad_wire(wire,(size_t)n,&sequence,&buttons,sticks))continue;
  if(seen&&!newer_sequence(sequence,last))continue;
  seen=1;last=sequence;if(pad_open()<0)continue;
  fill_pad_data(state,buttons,sticks,mono_us());int rv=sce.pad_insert(pad_device,state);held=1;
  static int reported;if(rv<0&&!reported){reported=1;CLOG("insert=%08x\n",rv);}
 }
}
static int control_socket(int type,int port){
 int s=socket(AF_INET,type,0);if(s<0)return -1;int one=1;setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&one,sizeof one);
 struct sockaddr_in a={0};a.sin_len=sizeof a;a.sin_family=AF_INET;a.sin_port=htons(port);a.sin_addr.s_addr=htonl(INADDR_ANY);
 if(bind(s,(struct sockaddr*)&a,sizeof a)<0||(type==SOCK_STREAM&&listen(s,1)<0)){close(s);return -1;}
 return s;
}
/* Console services answer over IPC and any of them could block, so they start on this thread and the capture never waits for them. */
static void*control_thread(void*unused){(void)unused;
 if(sce.user_init)CLOG("sceUserServiceInitialize=%08x\n",sce.user_init(0));
 if(sce.lnc_init)CLOG("sceLncUtilInitialize=%08x\n",sce.lnc_init());
 pthread_t thread;
 if(VIRTUAL_PAD_ENABLED){
  pad_socket=control_socket(SOCK_DGRAM,PAD_PORT);CLOG("pad socket=%d errno=%d\n",pad_socket,errno);
  if(pad_socket>=0&&pthread_create(&thread,0,pad_thread,0)==0)pthread_detach(thread);
 }
 control_listener=control_socket(SOCK_STREAM,CONTROL_PORT);CLOG("control listener=%d errno=%d\n",control_listener,errno);
 if(control_listener<0)return 0;
 for(;;){int fd=accept(control_listener,0,0);if(fd<0){if(errno==EINTR)continue;return 0;}control_session(fd);close(fd);}
}
/* Called once the capture session has a viewer. The SDK's kernel calls share one set of descriptors and are not safe across threads, so
   every symbol is looked up here on the main thread, and the other threads only ever call the results. If they cannot start, the stream carries on without them. */
static void control_start(load_fn load){
 /* The previous run's log is kept, because it is the only record of a run that did not end well. */
 rename("/data/playbridge-control.txt","/data/playbridge-control.old.txt");
 control_log=fopen("/data/playbridge-control.txt","w");
 uint32_t user=module(load,"libSceUserService.sprx"),service=module(load,"libSceSystemService.sprx"),pad=VIRTUAL_PAD_ENABLED?module(load,"libScePad.sprx"):0;
 sce.user_init=symbol(user,"sceUserServiceInitialize");sce.foreground=symbol(user,"sceUserServiceGetForegroundUser");
 sce.lnc_init=symbol(service,"sceLncUtilInitialize");sce.launch=symbol(service,"sceSystemServiceLaunchApp");sce.big_app=symbol(service,"sceLncUtilGetAppIdOfRunningBigApp");sce.title_of=symbol(service,"sceLncUtilGetAppTitleId");sce.kill=symbol(service,"sceLncUtilKillApp");
 sce.front=symbol(service,"sceLncUtilGetAppFocusedAppStatus");sce.rest=symbol(service,"sceSystemStateMgrEnterStandby");sce.off=symbol(service,"sceSystemStateMgrTurnOff");sce.reboot=symbol(service,"sceSystemStateMgrReboot");
 sce.pad_init=symbol(pad,"scePadInit");sce.pad_add=symbol(pad,"scePadVirtualDeviceAddDevice");sce.pad_insert=symbol(pad,"scePadVirtualDeviceInsertData");sce.pad_delete=symbol(pad,"scePadVirtualDeviceDeleteDevice");
 pthread_t thread;if(pthread_create(&thread,0,control_thread,0)==0)pthread_detach(thread);
}
static void control_stop(void){
 if(pad_device>=0&&sce.pad_delete)CLOG("delete pad=%08x\n",sce.pad_delete(pad_device));
 if(control_log)fclose(control_log);control_log=0;
}
