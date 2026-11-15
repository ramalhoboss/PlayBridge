/* Console side of the game library, status and power. Lives only as long as the capture session. The PC controller is not here: it has
   its own payload and process, pad-companion.c, so nothing it waits for can stop this port or the capture. */
#include <pthread.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <dirent.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include "control-rules.h"
int sceKernelGetCpuTemperature(int*);
int sceKernelGetSocSensorTemperature(int,int*);
/* It fills a 112-byte block (control-rules.h), never a single number. */
int sceKernelGetSocPowerConsumption(void*);
long sceKernelGetCpuFrequency(void);
static struct{
 int(*user_init)(void*);int(*foreground)(int*);int(*lnc_init)(void);
 int(*launch)(const char*,char**,void*);int(*big_app)(void);int(*title_of)(int,char*);int(*kill)(int);
 int(*front)(void*);int(*rest)(int);int(*off)(int);int(*reboot)(int);int(*ask_off)(int);int(*ask_reboot)(int);
}sce;
static FILE*control_log;
static int control_listener=-1;
#define CLOG(...) do{if(control_log){fprintf(control_log,__VA_ARGS__);fflush(control_log);}}while(0)
static void*symbol(uint32_t handle,const char*name){void*p=handle?(void*)kernel_dynlib_dlsym(-1,handle,name):0;CLOG("%s=%p\n",name,p);return p;}
static int control_write(int fd,const void*data,size_t n){const unsigned char*p=data;while(n){ssize_t w=send(fd,p,n,0);if(w<=0)return -1;p+=w;n-=(size_t)w;}return 0;}
static int control_read(int fd,void*data,size_t n){unsigned char*p=data;while(n){ssize_t r=recv(fd,p,n,0);if(r<=0)return -1;p+=r;n-=(size_t)r;}return 0;}
static int control_header(int fd,int result,uint32_t n){unsigned char h[12];memcpy(h,"PBR1",4);memcpy(h+4,&result,4);memcpy(h+8,&n,4);return control_write(fd,h,12);}
static int control_reply(int fd,int result,const void*body,uint32_t n){return control_header(fd,result,n)||(n&&control_write(fd,body,n))?-1:0;}
/* The newest game frame count. Its own thread reads it, so a display driver slow to answer can never hold up a status answer or the
   capture; the status answer only copies the latest reading. */
static pthread_mutex_t fps_lock=PTHREAD_MUTEX_INITIALIZER;
static struct{int state,error;uint64_t count,us;}fps_now={FPS_NO_DEVICE,0,0,0};
static int fps_fd=-1;
static int fps_request(uint64_t code,struct fps_request*arg){return ioctl(fps_fd,(unsigned long)code,arg)<0?errno:0;}
static void*fps_thread(void*unused){(void)unused;
 /* The block, then a page nobody may touch, made once. */
 unsigned char*block=mmap(0,FPS_BLOCK*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
 if(block==MAP_FAILED){CLOG("fps block errno=%d\n",errno);return 0;}
 if(mprotect(block+FPS_BLOCK,FPS_BLOCK,PROT_NONE)!=0){CLOG("fps guard errno=%d\n",errno);munmap(block,FPS_BLOCK*2);return 0;}
 int told=-1,told_error=-1;
 for(;;){
  int state,error=0;uint64_t count=0;
  if(fps_fd<0)fps_fd=open(FPS_DEVICE,O_RDWR);
  if(fps_fd<0){state=FPS_NO_DEVICE;error=errno;}
  /* After any failure the device is opened again for the next reading. */
  else{state=fps_read(fps_request,block,&count,&error);if(state!=FPS_OK){close(fps_fd);fps_fd=-1;}}
  uint64_t us=mono_us();
  if(state!=told||error!=told_error){CLOG("fps state=%d errno=%d count=%llu\n",state,error,(unsigned long long)count);told=state;told_error=error;}
  pthread_mutex_lock(&fps_lock);fps_now.state=state;fps_now.error=error;fps_now.count=count;fps_now.us=us;pthread_mutex_unlock(&fps_lock);
  /* Four readings a second with a game, like the status answers; one a second otherwise. */
  usleep(state==FPS_OK?250000:1000000);
 }
}
/* The fan target (control-rules.h). The console's own fan control keeps running; PlayBridge only lowers the temperature it aims for, and
   only while the PC is connected. The control thread reads it for the status answer, at most every FAN_READ_EVERY_US, and the main
   thread puts the console's own back when the payload stops, so the lock keeps the two apart. */
#define FAN_NOTE "/data/playbridge-fan.txt"
#define FAN_READ_EVERY_US 5000000ULL
static pthread_mutex_t fan_lock=PTHREAD_MUTEX_INITIALIZER;
static int fan_now=0,fan_own=0,fan_set=0;static uint64_t fan_read_us=0;
/* The block the two requests fill, far larger than the 28 bytes they move: a firmware that moved more would still land inside it. */
static _Alignas(16) unsigned char fan_block[256];
static int fan_request(unsigned long request){
 int fd=open(FAN_DEVICE,O_RDWR);if(fd<0)return errno?errno:EIO;
 int failed=ioctl(fd,request,fan_block)<0?(errno?errno:EIO):0;close(fd);return failed;
}
/* The target now, or minus the error. The block keeps the reading, for a change to send back. */
static int fan_read(void){
 memset(fan_block,0,sizeof fan_block);fan_block[FAN_SELECTOR_AT]=0;
 int failed=fan_request(FAN_GET);return failed?-failed:fan_block[FAN_TARGET_AT];
}
static void fan_keep_note(void){
 if(!fan_set){unlink(FAN_NOTE);return;}
 FILE*note=fopen(FAN_NOTE,"w");if(note){fprintf(note,"%d %d\n",fan_own,fan_set);fclose(note);}
}
/* After each reading. The first since this payload started takes the note an earlier copy left, if the target is still the one it set. */
static void fan_seen(int now){
 fan_now=now;if(now<=0)return;
 if(!fan_own){
  char text[32];size_t n=0;FILE*note=fopen(FAN_NOTE,"r");
  if(note){n=fread(text,1,sizeof text,note);fclose(note);}
  int own=0,set=0;
  if(n&&n<sizeof text&&fan_note(text,n,&own,&set)&&set==now){fan_own=own;fan_set=set;CLOG("fan note own=%d set=%d\n",own,set);return;}
  if(note)unlink(FAN_NOTE);
  fan_own=now;CLOG("fan target %d\n",now);return;
 }
 int had=fan_set;fan_follow(now,&fan_own,&fan_set);
 if(had&&!fan_set){CLOG("fan target %d is the console's own again\n",now);unlink(FAN_NOTE);}
}
static void fan_refresh(void){
 pthread_mutex_lock(&fan_lock);uint64_t us=mono_us();
 if(!fan_read_us||us-fan_read_us>=FAN_READ_EVERY_US){fan_read_us=us;int now=fan_read();if(now!=fan_now)CLOG("fan read %d\n",now);fan_seen(now);}
 pthread_mutex_unlock(&fan_lock);
}
/* A new target, or the console's own with 0, then read back. 0 once it is in place. */
static int fan_change(int want){
 int now=fan_read();fan_seen(now);fan_read_us=mono_us();if(now<0)return -now;
 if(!fan_target_allowed(want,fan_own))return EINVAL;
 int target=want?want:fan_own;
 if(target!=now){
  fan_block[FAN_TARGET_AT]=(unsigned char)target;int failed=fan_request(FAN_SET);CLOG("fan set %d -> %d: %d\n",now,target,failed);
  if(failed)return failed;
  int check=fan_read();fan_now=check;
  if(check!=target)return check<0?-check:EIO;
 }
 fan_set=target==fan_own?0:target;fan_now=target;fan_keep_note();return 0;
}
static int fan_target(int want){pthread_mutex_lock(&fan_lock);int result=fan_change(want);pthread_mutex_unlock(&fan_lock);return result;}
/* The console's own target back, when the PC leaves and when the payload stops: a lower one lasts only while PlayBridge is connected. */
static void fan_restore(void){
 pthread_mutex_lock(&fan_lock);
 if(fan_set){int result=fan_change(0);CLOG("fan back to %d: %d\n",fan_own,result);}
 pthread_mutex_unlock(&fan_lock);
}
/* Turn off and reboot go first as the request any app may make, which the console carries out as it does from its own Power menu: it
   closes the game and its apps, then goes (ShellCore's shutdown types SYSTEM_SERVICE_POWER_OFF and SYSTEM_SERVICE_REBOOT). The lower
   system state call, which the console's menu makes only at the end of its own sequence, is the fallback. 0 once one was taken. */
static int power_call(const char*what,int(*ask)(int),int(*direct)(int)){
 int rv=ENOSYS;
 if(ask){rv=ask(0);CLOG("%s request rv=%08x\n",what,rv);if(rv==0)return 0;}
 if(direct){rv=direct(0);CLOG("%s rv=%08x\n",what,rv);}
 return rv;
}
static int foreground_user(void){int user=-1;if(sce.foreground&&sce.foreground(&user)<0)user=-1;return user;}
static void json_safe_title(char*title){title[15]=0;for(int i=0;title[i];i++)if(title[i]<' '||title[i]=='"'||title[i]=='\\')title[i]='?';}
static int control_status(int fd){
 /* Sensor 0 is the SoC's own. A getter that did not read its sensor leaves NO_READING for the PC (control-rules.h). */
 int cpu=NO_READING,soc=NO_READING,app=-1;char title[16]={0};
 int cpu_result=sceKernelGetCpuTemperature(&cpu);int soc_result=sceKernelGetSocSensorTemperature(0,&soc);
 cpu=temperature_reading(cpu_result,cpu);soc=temperature_reading(soc_result,soc);
 /* Read after the temperatures, into a block of its own far larger than the getter writes; static, as only this thread answers STATUS. */
 static _Alignas(16) unsigned char power_block[POWER_BLOCK];memset(power_block,0,sizeof power_block);
 int power[3];power_parts(sceKernelGetSocPowerConsumption(power_block),power_block,power);
 if(sce.big_app){app=sce.big_app();if(app>0&&sce.title_of&&sce.title_of(app,title)<0)title[0]=0;}
 /* The app on the screen, which is the console's menu while the PS button has it over a game. The title id sits at +16 and the full size of this answer is not known, so there is plenty of room. */
 static unsigned char focus[512];char front[16]={0};if(sce.front&&sce.front(focus)==0)memcpy(front,focus+16,15);
 json_safe_title(title);json_safe_title(front);
 pthread_mutex_lock(&fps_lock);int fps_state=fps_now.state;uint64_t flips=fps_now.count,flips_us=fps_now.us;pthread_mutex_unlock(&fps_lock);
 fan_refresh();pthread_mutex_lock(&fan_lock);int fan[3]={fan_now,fan_own,fan_set};pthread_mutex_unlock(&fan_lock);
 /* Every field at its widest still fits; a cut answer would not be JSON and would end the link. */
 char body[512];int n=snprintf(body,sizeof body,"{\"cpu_c\":%d,\"soc_c\":%d,\"gpu_mw\":%d,\"cpu_mw\":%d,\"mem_mw\":%d,\"cpu_mhz\":%ld,\"user\":%d,\"app\":%d,\"title\":\"%s\",\"front\":\"%s\",\"fps_state\":%d,\"flips\":%llu,\"flips_us\":%llu,\"fan_c\":%d,\"fan_own\":%d,\"fan_set\":%d}",cpu,soc,power[0],power[1],power[2],sceKernelGetCpuFrequency()/1000000,foreground_user(),app,title,front,fps_state,(unsigned long long)flips,(unsigned long long)flips_us,fan[0],fan[1],fan[2]);
 if(n<0||n>=(int)sizeof body)return control_reply(fd,EMSGSIZE,0,0);
 return control_reply(fd,0,body,(uint32_t)n);
}
static int control_file(int fd,const char*path,uint32_t length){
 if(!allowed_file(path,length))return control_reply(fd,EACCES,0,0);
 int file=open(path,O_RDONLY);if(file<0)return control_reply(fd,errno,0,0);
 /* Game files stay small. A clip or a save can be large, but the reply's size field holds at most 4 GB. */
 struct stat info;int failed=fstat(file,&info)<0||info.st_size>(capture_file(path,length)||save_file(path,length)?0xfffffffeLL:0x10000000LL);
 if(failed){close(file);return control_reply(fd,EFBIG,0,0);}
 uint32_t left=(uint32_t)info.st_size;if(control_header(fd,0,left)<0){close(file);return -1;}
 static unsigned char chunk[0x10000];
 while(left){ssize_t r=read(file,chunk,left<sizeof chunk?left:sizeof chunk);if(r<=0||control_write(fd,chunk,(size_t)r)<0){close(file);return -1;}left-=(uint32_t)r;
  /* About 4 MB/s, so a refresh does not take the Wi-Fi away from the video. */
  usleep(16000);}
 close(file);return 0;
}
/* Part of a file, as slowly as a whole one. Past the end it is shorter, or empty. */
static int control_range(int fd,const char*body,uint32_t length){
 uint64_t offset;uint32_t want;
 if(!range_request(body,length,&offset,&want))return control_reply(fd,EACCES,0,0);
 const char*path=body+12;int file=open(path,O_RDONLY);if(file<0)return control_reply(fd,errno,0,0);
 struct stat info;if(fstat(file,&info)<0){int e=errno;close(file);return control_reply(fd,e,0,0);}
 uint64_t size=(uint64_t)info.st_size;uint32_t left=offset>=size?0:(uint32_t)(size-offset<want?size-offset:want);
 if(left&&lseek(file,(off_t)offset,SEEK_SET)<0){int e=errno;close(file);return control_reply(fd,e,0,0);}
 if(control_header(fd,0,left)<0){close(file);return -1;}
 static unsigned char part[0x10000];
 while(left){ssize_t r=read(file,part,left<sizeof part?left:sizeof part);if(r<=0||control_write(fd,part,(size_t)r)<0){close(file);return -1;}left-=(uint32_t)r;usleep(16000);}
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
  else if(command==CONTROL_RANGE)failed=control_range(fd,body,length);
  else if(command==CONTROL_FAN)failed=control_reply(fd,length==1?fan_target((unsigned char)body[0]):EINVAL,0,0);
  else if(command==CONTROL_LAUNCH)failed=control_reply(fd,control_launch(body,length),0,0);
  else if(command==CONTROL_CLOSE)failed=control_reply(fd,control_close(),0,0);
  /* These answer once the console has taken them, with its own result, so the PC can say when it refused. A console already on its way
     may never answer, and the PC takes that as going. */
  else if(command==CONTROL_REST)failed=control_reply(fd,power_call("standby",0,sce.rest),0,0);
  else if(command==CONTROL_POWER_OFF)failed=control_reply(fd,power_call("turn off",sce.ask_off,sce.off),0,0);
  else if(command==CONTROL_REBOOT)failed=control_reply(fd,power_call("reboot",sce.ask_reboot,sce.reboot),0,0);
  else failed=control_reply(fd,EINVAL,0,0);
  if(failed)return;
 }
}
static int control_socket(int port){
 int s=socket(AF_INET,SOCK_STREAM,0);if(s<0)return -1;int one=1;setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&one,sizeof one);
 struct sockaddr_in a={0};a.sin_len=sizeof a;a.sin_family=AF_INET;a.sin_port=htons(port);a.sin_addr.s_addr=htonl(INADDR_ANY);
 if(bind(s,(struct sockaddr*)&a,sizeof a)<0||listen(s,1)<0){close(s);return -1;}
 return s;
}
/* Console services answer over IPC and any of them could block, so they start on this thread and the capture never waits for them. */
static void*control_thread(void*unused){(void)unused;
 if(sce.user_init)CLOG("sceUserServiceInitialize=%08x\n",sce.user_init(0));
 if(sce.lnc_init)CLOG("sceLncUtilInitialize=%08x\n",sce.lnc_init());
 control_listener=control_socket(CONTROL_PORT);CLOG("control listener=%d errno=%d\n",control_listener,errno);
 if(control_listener<0)return 0;
 for(;;){int fd=accept(control_listener,0,0);if(fd<0){if(errno==EINTR)continue;return 0;}control_session(fd);close(fd);fan_restore();}
}
/* Called once the capture session has a viewer. The SDK's kernel calls share one set of descriptors and are not safe across threads, so
   every symbol is looked up here on the main thread, and the other threads only ever call the results. If they cannot start, the stream carries on without them. */
static void control_start(load_fn load){
 /* The previous run's log is kept, because it is the only record of a run that did not end well. */
 rename("/data/playbridge-control.txt","/data/playbridge-control.old.txt");
 control_log=fopen("/data/playbridge-control.txt","w");
 uint32_t user=module(load,"libSceUserService.sprx"),service=module(load,"libSceSystemService.sprx");
 sce.user_init=symbol(user,"sceUserServiceInitialize");sce.foreground=symbol(user,"sceUserServiceGetForegroundUser");
 sce.lnc_init=symbol(service,"sceLncUtilInitialize");sce.launch=symbol(service,"sceSystemServiceLaunchApp");sce.big_app=symbol(service,"sceLncUtilGetAppIdOfRunningBigApp");sce.title_of=symbol(service,"sceLncUtilGetAppTitleId");sce.kill=symbol(service,"sceLncUtilKillApp");
 sce.front=symbol(service,"sceLncUtilGetAppFocusedAppStatus");sce.rest=symbol(service,"sceSystemStateMgrEnterStandby");sce.off=symbol(service,"sceSystemStateMgrTurnOff");sce.reboot=symbol(service,"sceSystemStateMgrReboot");
 sce.ask_off=symbol(service,"sceSystemServiceRequestPowerOff");sce.ask_reboot=symbol(service,"sceSystemServiceRequestReboot");
 pthread_t thread;if(pthread_create(&thread,0,control_thread,0)==0)pthread_detach(thread);
 pthread_t reader;if(pthread_create(&reader,0,fps_thread,0)==0)pthread_detach(reader);
}
static void control_stop(void){
 fan_restore();
 if(control_log)fclose(control_log);control_log=0;
}
