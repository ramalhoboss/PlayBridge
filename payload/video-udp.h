/* The payload's side of the picture and sound over UDP, for play away from home (fec-rules.h has the format, away-rules.h the rules,
   app/udp_video.py the PC's side). The PC asks for it in its options, only over a connection that proved the key. The acknowledgement
   still goes over that TCP connection, which stays open for the whole stream; every record after it goes as sealed datagrams to the
   address the PC's reports come from, so a PC behind a router anywhere is reached the way it reached the console.

   The part above VIDEO_UDP_RULES_ONLY makes the datagrams and takes the reports with no socket, so the PC's tests build it as it is. */
#ifndef VIDEO_UDP_H
#define VIDEO_UDP_H
#include "fec-rules.h"
#include "away-rules.h"
#define VIDEO_UDP_PORT 9076
#define VIDEO_UDP_START_PERCENT 20u
struct video_udp{
 int fd,peer;uint32_t peer_address;uint16_t peer_port;
 struct secure_dir to_pc,from_pc;uint32_t number;unsigned percent;uint64_t started_ms,heard_ms,sent,send_failed,reports;
 unsigned char parity[FEC_BLOCK*FEC_FRAGMENT],plain[FEC_DATAGRAM],datagram[FEC_DATAGRAM+SECURE_DATAGRAM_EXTRA];
};
typedef int(*video_udp_emit)(void*ctx,const unsigned char*datagram,size_t n);
/* The keys from the video connection's handshake, and a fresh start. */
SECURE_PART static void video_udp_keys(struct video_udp*u,const unsigned char key[32],const unsigned char ns[16],const unsigned char nc[16],uint64_t now_ms){
 fec_init();secure_keys(key,SECURE_VIDEO_UDP,ns,nc,&u->from_pc,&u->to_pc);
 u->number=0;u->percent=VIDEO_UDP_START_PERCENT;u->peer=0;u->peer_address=0;u->peer_port=0;u->started_ms=now_ms;u->heard_ms=0;u->sent=u->send_failed=u->reports=0;
}
/* Every datagram of one record, sealed, each handed to emit in the order the PC expects: a block's data, then its parity. */
SECURE_PART static int video_udp_record(struct video_udp*u,const unsigned char*record,uint32_t size,video_udp_emit emit,void*ctx){
 struct fec_plan p;fec_plan(&p,size,u->percent);uint32_t number=u->number++;
 for(uint32_t b=0;b<p.blocks;b++){
  unsigned k=fec_data_in(&p,b),m=fec_parity_in(&p,b);
  if(m)fec_parity(&p,record,b,u->parity);
  for(unsigned i=0;i<k+m;i++){
   size_t n=fec_fragment(&p,number,record,u->parity,b,i,u->plain);
   if(emit(ctx,u->datagram,secure_seal_datagram(&u->to_pc,u->plain,n,u->datagram))<0)return -1;
  }
 }
 return 0;
}
/* A datagram that came to the UDP port: 1 when it is the PC's report, which says where to send and how much parity it wants. address
   and port are where it came from, in network order. Anything else, or a report seen before, changes nothing. */
SECURE_PART static int video_udp_take(struct video_udp*u,unsigned char*w,size_t n,uint32_t address,uint16_t port,uint64_t now_ms){
 long m=secure_open_datagram(&u->from_pc,w,n);unsigned percent;
 if(m<0||!fec_report(w+12,m,&percent))return 0;
 u->percent=percent;u->heard_ms=now_ms;u->peer=1;u->peer_address=address;u->peer_port=port;u->reports++;return 1;
}

#ifndef VIDEO_UDP_RULES_ONLY
#include <fcntl.h>
/* Sends go out at most this many times the stream's bitrate, so a large picture does not reach the home router all at once. */
#define VIDEO_UDP_PACE 4u
static uint64_t video_udp_pace_bps,video_udp_free_us;
static uint64_t video_udp_us(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000+(uint64_t)t.tv_nsec/1000;}
/* The UDP port, for one stream: 0 once open, -1 when it cannot be (the stream then stays on TCP). */
static int video_udp_open(struct video_udp*u,uint32_t bitrate){
 int s=socket(AF_INET,SOCK_DGRAM,0);if(s<0)return -1;
 int one=1;setsockopt(s,SOL_SOCKET,SO_REUSEADDR,&one,sizeof one);int size=2<<20;setsockopt(s,SOL_SOCKET,SO_SNDBUF,&size,sizeof size);
 struct sockaddr_in a={0};a.sin_len=sizeof a;a.sin_family=AF_INET;a.sin_port=htons(VIDEO_UDP_PORT);a.sin_addr.s_addr=htonl(INADDR_ANY);
 if(bind(s,(struct sockaddr*)&a,sizeof a)<0){close(s);return -1;}
 fcntl(s,F_SETFL,fcntl(s,F_GETFL,0)|O_NONBLOCK);
 u->fd=s;video_udp_pace_bps=(uint64_t)bitrate*VIDEO_UDP_PACE;video_udp_free_us=0;return 0;
}
static void video_udp_close(struct video_udp*u){if(u->fd>=0)close(u->fd);u->fd=-1;u->peer=0;}
/* Reads every report waiting, without waiting for one. */
static void video_udp_poll(struct video_udp*u,uint64_t now_ms){
 for(;;){
  unsigned char w[128];struct sockaddr_in from;socklen_t size=sizeof from;
  ssize_t n=recvfrom(u->fd,w,sizeof w,0,(struct sockaddr*)&from,&size);
  if(n<=0)return;
  video_udp_take(u,w,(size_t)n,from.sin_addr.s_addr,from.sin_port,now_ms);
 }
}
static int video_udp_emit_to(void*ctx,const unsigned char*d,size_t n){
 struct video_udp*u=ctx;struct sockaddr_in to={0};to.sin_len=sizeof to;to.sin_family=AF_INET;to.sin_addr.s_addr=u->peer_address;to.sin_port=u->peer_port;
 /* Pacing: each datagram has its time at the paced rate; more than 2 ms ahead of it waits the difference. */
 uint64_t now=video_udp_us();if(video_udp_free_us<now)video_udp_free_us=now;
 if(video_udp_pace_bps)video_udp_free_us+=(uint64_t)n*8u*1000000u/video_udp_pace_bps;
 if(video_udp_free_us>now+2000)usleep((useconds_t)(video_udp_free_us-now-1000));
 for(int tries=0;tries<4;tries++){
  if(sendto(u->fd,d,n,0,(struct sockaddr*)&to,sizeof to)>=0){u->sent++;return 0;}
  if(errno!=ENOBUFS&&errno!=EAGAIN)break;
  usleep(500);
 }
 /* A datagram the system could not take is one more loss for the parity: the stream goes on. */
 u->send_failed++;return 0;
}
/* Waits, wait_ms at most, for the PC's first report: 1 once it has come, 0 when it did not. */
static int video_udp_wait_peer(struct video_udp*u,uint64_t(*now_ms)(void),uint32_t wait_ms){
 uint64_t end=now_ms()+wait_ms;
 while(!u->peer){
  uint64_t now=now_ms();if(now>=end)return 0;
  uint64_t left=end-now;struct pollfd p={u->fd,POLLIN,0};poll(&p,1,left<20?(int)left:20);video_udp_poll(u,now_ms());
 }
 return 1;
}
/* One record to the PC. Before its first report the PC's address is not known yet, and the record is left out. */
static int video_udp_send(struct video_udp*u,const unsigned char*record,uint32_t size){
 if(!u->peer)return 0;
 return video_udp_record(u,record,size,video_udp_emit_to,u);
}
#endif
#endif
