/* Play away from home. Nothing here goes to the PS5 from outside the home: the PC sends this payload on the home network, through the
   loader, which is never opened to the internet. When it wrote the away flag next to its key (secure-rules.h), the payload stays
   after a stream ends and waits for the same PC again, up to the hours in the flags, so the PC can stream from anywhere it reaches
   the console: a port its router forwards, or a Tailscale route to the home network.

   Every connection still proves the key first. A payload that holds no key, as one loaded by hand, only ever answers addresses of a
   home network or of a tunnel to one, so a port left forwarded never opens it to the internet.

   Freestanding, with no library: the payload and the PC's tests build the same file. */
#ifndef AWAY_RULES_H
#define AWAY_RULES_H
#include <stdint.h>
#define AWAY_FLAG 1u
#define AWAY_HOURS_USUAL 12u
#define AWAY_HOURS_MOST 72u
/* Waiting for the PC goes in slices this long, so a request to end it is seen at once. */
#define AWAY_SLICE_MS 1000
/* A stream over UDP ends when the PC has not been heard for this long: its reports come four times a second. */
#define AWAY_PC_SILENT_MS 8000u
/* The first report must come this soon after the capture started. */
#define AWAY_FIRST_REPORT_MS 10000u
/* Before the capture starts, the PC's first report is waited for this long at most: until it comes the payload does not know where to
   send, and the first picture, the keyframe the PC needs, would be left out (measured on the PS5 2026-11-16: the PC then waited about
   a second for the next one). */
#define UDP_FIRST_REPORT_WAIT_MS 1000u
#define AWAY_PART __attribute__((unused))

/* Whether this payload waits for its PC after a stream: only with a key. */
AWAY_PART static int away_on(int keyed,uint32_t flags){return keyed&&(flags&AWAY_FLAG);}
/* How long it waits, from the flags' second byte, in hours: 0 is the usual 12, and never more than 72. */
AWAY_PART static uint32_t away_hours(uint32_t flags){uint32_t h=(flags>>8)&0xffu;return !h?AWAY_HOURS_USUAL:h>AWAY_HOURS_MOST?AWAY_HOURS_MOST:h;}
AWAY_PART static uint64_t away_wait_ms(uint32_t flags){return (uint64_t)away_hours(flags)*3600000u;}
/* An IPv4 address (in host order) of a home network or a tunnel to one: 10/8, 172.16/12, 192.168/16, 169.254/16, 127/8, and 100.64/10
   for Tailscale. */
AWAY_PART static int away_local(uint32_t a){
 return (a>>24)==10u||(a>>24)==127u||(a>>20)==0xac1u||(a>>16)==0xc0a8u||(a>>16)==0xa9feu||(a>>22)==0x191u;
}
/* Whether a connection may go on: always with the key, since it is proved next; without one, only from a home address. */
AWAY_PART static int away_admit(int keyed,uint32_t peer){return keyed||away_local(peer);}
/* The UDP stream's state after its last report: 1 while the PC is heard, 0 once it went quiet. heard is 0 before the first report. */
AWAY_PART static int away_pc_heard(uint64_t now_ms,uint64_t started_ms,uint64_t heard_ms){
 if(!heard_ms)return now_ms-started_ms<AWAY_FIRST_REPORT_MS;
 return now_ms-heard_ms<AWAY_PC_SILENT_MS;
}
#endif
