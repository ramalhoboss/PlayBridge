/* The console side of the secured link (secure-rules.h says how it works). A payload holds this PC's key only when the PC that sent it
   wrote one into secure_slot; with none, every port works as before. With one, every connection proves the key first, within
   SECURE_WAIT_MS, and every byte after that goes sealed. A connection that cannot prove it is closed and the port waits for the next:
   nothing anybody sends can end the payload or reach the console. */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <errno.h>
#include <time.h>
#include <poll.h>
#include <unistd.h>
#include <sys/types.h>
#include <sys/time.h>
#include <sys/socket.h>
#include <sys/sysctl.h>
#include <netinet/in.h>
#include "secure-rules.h"
#define SECURE_WAIT_MS 3000
/* The PC finds this place by its first 16 bytes and writes the key and flags into it before sending the payload. */
__attribute__((used)) static volatile unsigned char secure_slot[SECURE_SLOT_SIZE]={'P','B','K','E','Y','S','L','O','T','1'};
static unsigned char secure_key[32];static uint32_t secure_flags;static int secure_on;
static uint64_t secure_now_ms(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000+(uint64_t)t.tv_nsec/1000000;}
/* Trace (SECURE_FLAG_TRACE): set only by a test tool on the PC, never by PlayBridge itself. */
static int secure_trace;static uint64_t secure_started_ms;
static void secure_start(void){
 secure_on=secure_key_of(secure_slot,secure_key,&secure_flags);
 secure_trace=secure_on&&(secure_flags&SECURE_FLAG_TRACE);
 if(secure_trace&&!secure_started_ms){
  /* The test tool may close its end at any time: a write then fails rather than ending the payload, and one it does not read soon
     enough gives up after a fifth of a second rather than holding the capture. */
  signal(SIGPIPE,SIG_IGN);struct timeval limit={0,200000};setsockopt(1,SOL_SOCKET,SO_SNDTIMEO,&limit,sizeof limit);
  secure_started_ms=secure_now_ms();
 }
}
/* One log line: into file when there is one, and with trace on to the standard output too, with the seconds since the payload started
   and the log's name in front. The arguments are worked out once, as some are console calls whose answer is written down. */
SECURE_PART __attribute__((format(printf,3,4))) static void secure_log(FILE*file,const char*from,const char*format,...){
 char line[1024];va_list list;va_start(list,format);int n=vsnprintf(line,sizeof line,format,list);va_end(list);
 if(n<0)return;
 const char*end=n>0&&n<(int)sizeof line&&line[n-1]=='\n'?"":"\n";
 if(file){fputs(line,file);fputs(end,file);fflush(file);}
 if(!secure_trace)return;
 /* A line that already names its log, as the control log's do, is not named twice. */
 char out[1100];uint64_t ms=secure_now_ms()-secure_started_ms;size_t named=strlen(from);
 if(!strncmp(line,from,named)&&line[named]==':')from="";
 snprintf(out,sizeof out,"%llu.%03llu %s%s%s%s",(unsigned long long)(ms/1000),(unsigned long long)(ms%1000),from,*from?": ":"",line,end);
 fputs(out,stdout);fflush(stdout);
}
/* A number no connection had before: the kernel's random bytes, the time and a count, through SHA-256. */
static void secure_fresh(unsigned char out[16]){
 static uint64_t made;unsigned char random[32]={0};size_t size=sizeof random;int mib[2]={CTL_KERN,KERN_ARND};
 sysctl(mib,2,random,&size,0,0);
 struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);uint64_t count=__atomic_add_fetch(&made,1,__ATOMIC_RELAXED);pid_t pid=getpid();
 struct secure_sha s;unsigned char digest[32];secure_sha_init(&s);secure_sha_add(&s,random,sizeof random);secure_sha_add(&s,&t,sizeof t);
 secure_sha_add(&s,&count,sizeof count);secure_sha_add(&s,&pid,sizeof pid);secure_sha_end(&s,digest);
 for(int i=0;i<16;i++)out[i]=digest[i];
}
/* All n bytes, or -1. With a deadline (ms, 0 for none), a connection that sends slowly cannot hold the port past it. For the logs, errno
   says why: ETIMEDOUT past the deadline, ECONNRESET when the other side closed, else the system's own. */
SECURE_PART static int secure_send_all(int fd,const unsigned char*p,size_t n){while(n){ssize_t w=send(fd,p,n,0);if(w<=0){if(!w)errno=ECONNRESET;return -1;}p+=w;n-=(size_t)w;}return 0;}
SECURE_PART static int secure_recv_all(int fd,unsigned char*p,size_t n,uint64_t deadline){
 while(n){
  if(deadline){
   uint64_t now=secure_now_ms();if(now>=deadline){errno=ETIMEDOUT;return -1;}
   struct pollfd w={fd,POLLIN,0};int ready=poll(&w,1,(int)(deadline-now));
   if(ready==0)errno=ETIMEDOUT;
   if(ready<=0)return -1;
  }
  ssize_t r=recv(fd,p,n,0);if(r<=0){if(!r)errno=ECONNRESET;return -1;}p+=r;n-=(size_t)r;
 }
 return 0;
}
/* One connection: its descriptor once the PC proved the key (live), its two directions and room for one record each way. A link that
   is all zero, as a static one starts, stands for no connection. */
struct secure_link{int live,fd;struct secure_dir to_pc,from_pc;unsigned char*out,*in;size_t have,at;unsigned char ns[16],nc[16];};
/* Where a handshake stopped, for the logs: no memory, the hello did not go, no answer came in time (or the PC closed), the answer did not
   prove the key, the proof did not go. */
enum{SECURE_FAIL_MEMORY=-1,SECURE_FAIL_HELLO=-2,SECURE_FAIL_ANSWER=-3,SECURE_FAIL_KEY=-4,SECURE_FAIL_PROOF=-5};
SECURE_PART static const char*secure_failure(int code){
 return code==SECURE_FAIL_MEMORY?"no memory":code==SECURE_FAIL_HELLO?"hello not sent":code==SECURE_FAIL_ANSWER?"no answer":code==SECURE_FAIL_KEY?"another key":code==SECURE_FAIL_PROOF?"proof not sent":"?";
}
/* The handshake on a connection just accepted: 0 once the PC proved the key, else a SECURE_FAIL_ step, and the connection is closed. */
SECURE_PART static int secure_accept(struct secure_link*l,int fd,int channel){
 l->live=0;l->have=l->at=0;
 if(!l->out)l->out=malloc(SECURE_RECORD_MAX+SECURE_RECORD_EXTRA);
 if(!l->in)l->in=malloc(SECURE_RECORD_MAX+SECURE_RECORD_EXTRA);
 if(!l->out||!l->in)return SECURE_FAIL_MEMORY;
 unsigned char ns[16],hello[SECURE_HELLO_SIZE],answer[SECURE_ANSWER_SIZE],proof[SECURE_PROOF_SIZE];
 secure_fresh(ns);secure_hello(hello,channel,ns);
 uint64_t deadline=secure_now_ms()+SECURE_WAIT_MS;
 if(secure_send_all(fd,hello,sizeof hello)<0)return SECURE_FAIL_HELLO;
 if(secure_recv_all(fd,answer,sizeof answer,deadline)<0)return SECURE_FAIL_ANSWER;
 if(!secure_check_answer(secure_key,channel,ns,answer,&l->from_pc,&l->to_pc,proof))return SECURE_FAIL_KEY;
 if(secure_send_all(fd,proof,sizeof proof)<0)return SECURE_FAIL_PROOF;
 /* The two numbers make the keys of the stream over UDP, when the PC asks for one. */
 memcpy(l->ns,ns,16);memcpy(l->nc,answer+4,16);
 l->fd=fd;l->live=1;return 0;
}
/* An IPv4 address (host order) as text, for the logs. */
SECURE_PART static const char*secure_address(uint32_t a,char out[16]){snprintf(out,16,"%u.%u.%u.%u",a>>24,(a>>16)&255u,(a>>8)&255u,a&255u);return out;}
SECURE_PART static int secure_write(struct secure_link*l,const void*data,size_t n){
 const unsigned char*p=data;
 while(n){
  uint32_t m=n<SECURE_RECORD_MAX?(uint32_t)n:SECURE_RECORD_MAX;size_t size=secure_seal_record(&l->to_pc,p,m,l->out);
  if(secure_send_all(l->fd,l->out,size)<0)return -1;
  p+=m;n-=m;
 }
 return 0;
}
/* n plain bytes from the PC, opening records as they come. A record that does not open ends the connection. */
SECURE_PART static int secure_read(struct secure_link*l,void*data,size_t n){
 unsigned char*p=data;
 while(n){
  if(l->at==l->have){
   if(secure_recv_all(l->fd,l->in,4,0)<0)return -1;
   uint32_t size=secure_record_length(l->in);
   if(!size||secure_recv_all(l->fd,l->in+4,size+SECURE_TAG,0)<0||!secure_open_record(&l->from_pc,l->in,size))return -1;
   l->at=4;l->have=4+size;
  }
  size_t k=l->have-l->at;if(k>n)k=n;
  memcpy(p,l->in+l->at,k);l->at+=k;p+=k;n-=k;
 }
 return 0;
}
/* Writes and reads on fd: through its link when it has one; plain only while this payload holds no key. */
SECURE_PART static int link_write(struct secure_link*l,int fd,const void*data,size_t n){
 if(l&&l->live&&l->fd==fd)return secure_write(l,data,n);
 if(secure_on)return -1;
 return secure_send_all(fd,data,n);
}
SECURE_PART static int link_read(struct secure_link*l,int fd,void*data,size_t n){
 if(l&&l->live&&l->fd==fd)return secure_read(l,data,n);
 if(secure_on)return -1;
 return secure_recv_all(fd,data,n,0);
}
/* The IPv4 address (host order) at the other end of a connection, 0 when it is not known. */
SECURE_PART static uint32_t link_peer(int fd){struct sockaddr_in a;socklen_t n=sizeof a;if(getpeername(fd,(struct sockaddr*)&a,&n)<0||a.sin_family!=AF_INET)return 0;return ntohl(a.sin_addr.s_addr);}
/* The connection is done: its link no longer stands for that descriptor. */
SECURE_PART static void link_end(struct secure_link*l){if(l)l->live=0;}
