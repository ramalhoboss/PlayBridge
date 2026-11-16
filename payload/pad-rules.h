/* What the controller companion accepts, what it answers and when it gives up. The companion runs as its own process on its own port, so
   nothing it waits for can hold the video, the control port or the capture. No console calls here, so the PC tests run this file directly.
   Each PC or phone that sends states is a controller of its own on the PS5, up to four, the most a PS5 takes. */
#ifndef PAD_PORT
#define PAD_PORT 9078
#endif
#define PAD_SLOTS 4
/* One controller state from a PC. Sticks and triggers use the console's own 0-255 ranges. */
#define PAD_WIRE_SIZE 20u
#define PAD_BUTTONS 0x0011fffeu
static int read_pad_wire(const unsigned char*w,size_t n,uint32_t*sequence,uint32_t*buttons,unsigned char*sticks){
 if(n!=PAD_WIRE_SIZE||w[0]!='P'||w[1]!='B'||w[2]!='P'||w[3]!='1')return 0;
 memcpy(sequence,w+4,4);memcpy(buttons,w+8,4);*buttons&=PAD_BUTTONS;memcpy(sticks,w+12,6);return 1;
}
/* A sender stops playing: its controller lets go of every button and is removed at once. The companion stays for the next press. */
#define PAD_QUIT_SIZE 8u
static int is_pad_quit(const unsigned char*w,size_t n){return n==PAD_QUIT_SIZE&&w[0]=='P'&&w[1]=='B'&&w[2]=='Q'&&w[3]=='1';}
/* Is a companion running here? A new copy that finds the port taken asks this first. The answer is the state, for no controller, and it
   neither makes a controller nor keeps the companion from ending. */
#define PAD_PROBE_SIZE 8u
static int is_pad_probe(const unsigned char*w,size_t n){return n==PAD_PROBE_SIZE&&w[0]=='P'&&w[1]=='B'&&w[2]=='H'&&w[3]=='1';}
/* A later sequence number, allowing for wrap-around. UDP can reorder, and an old state must not undo a newer one. */
static int newer_sequence(uint32_t now,uint32_t last){return (int32_t)(now-last)>0;}
/* The controller is made with requests on /dev/hid, the device libScePad itself reads, so it needs no scePadInit: inside a payload process
   on 13.60 that call waits on the console's Mbus service and never came back. The request numbers and the two 0xA8-byte blocks are the
   ones ProsperoSunshine (Darkatek7) measured and ps5upload's Play Together uses on 13.60. Each request's size is in its number, bits 16-28. */
#define PAD_HID_ADD 0xC018482Aul
#define PAD_HID_INSERT 0x8018482Cul
#define PAD_HID_DELETE 0x80104850ul
#define PAD_BLOCK_SIZE 0xA8u
struct pad_add_request{uint32_t op,unused;uint64_t description,handle;};
struct pad_insert_request{uint32_t handle,unused;uint64_t state;unsigned char zero,spare[7];};
struct pad_delete_request{unsigned char op,spare[7];uint32_t handle,unused;};
_Static_assert(sizeof(struct pad_add_request)==((PAD_HID_ADD>>16)&0x1fff),"the add request's size");
_Static_assert(sizeof(struct pad_insert_request)==((PAD_HID_INSERT>>16)&0x1fff),"the insert request's size");
_Static_assert(sizeof(struct pad_delete_request)==((PAD_HID_DELETE>>16)&0x1fff),"the delete request's size");
enum{PAD_OP_ADD=3,PAD_OP_DELETE=5};
static void clear_block(unsigned char*d){for(size_t i=0;i<PAD_BLOCK_SIZE;i++)d[i]=0;}
/* What is added: a standard controller (class 3, subtype 1) for one console user. */
static void pad_description(unsigned char*d,uint32_t user){clear_block(d);d[0]=3;memcpy(d+0x1c,&user,4);d[0x20]=1;}
/* One whole state: buttons, sticks and triggers, present, then a level controller at rest (orientation 0,0,0,1 and gravity 0,1,0). */
static void fill_pad_state(unsigned char*d,uint32_t buttons,const unsigned char*sticks){
 static const unsigned char one[4]={0,0,0x80,0x3f};
 clear_block(d);memcpy(d+0x0c,&buttons,4);memcpy(d+0x10,sticks,6);d[0x17]=1;memcpy(d+0x84,one,4);memcpy(d+0x98,one,4);
}
/* The answer to a sender: 'PBS2', where its controller stands, an error code, the newest sequence taken and which of the companion's
   controllers is its own (1 to 4, 0 before it has one). The PC never waits for it. */
#define PAD_STATUS_SIZE 20u
enum{PAD_STARTING=0,PAD_READY=1,PAD_FAILED=2};
static void pad_status_wire(unsigned char*w,uint32_t state,int32_t error,uint32_t sequence,uint32_t player){
 memcpy(w,"PBS2",4);memcpy(w+4,&state,4);memcpy(w+8,&error,4);memcpy(w+12,&sequence,4);memcpy(w+16,&player,4);
}
/* Errors of the companion's own, beside the console's 8xxxxxxx codes: 'PB' then a number. */
#define PAD_MISSING ((int32_t)0x50420001)   /* a call was not found, or the start-up thread did not start */
#define PAD_NO_USER ((int32_t)0x50420002)   /* nobody is signed in on the console */
#define PAD_NO_DEVICE ((int32_t)0x50420003) /* the console added no controller */
#define PAD_START_HUNG ((int32_t)0x50420004)/* starting the controller did not come back in time */
#define PAD_FULL ((int32_t)0x50420005)      /* four controllers are in use already */
#define PAD_NO_SEAT ((int32_t)0x50420006)   /* the console's Mbus service is not ready: the PS5 asks who is using the controller */
#define PAD_SEAT_OTHER ((int32_t)0x50420007)/* the console names another user as the controller's owner */
/* A new controller belongs to nobody, and the PS5 asks "Who is using this controller?" on its first PS press; a question left open stays
   on the screen even after that controller is removed (seen on the PS5). So the first controller is seated in the user in front at once,
   through the console's Mbus service, as ProsperoSunshine and ps5upload do: the PC that controls the console never sees the question.
   The other controllers are other players, whom the PS5 asks; each one answers with its own controller. A seat is only taken in the
   first moments after the add, and Mbus answers "no such device" until it has seen the new controller, so it is asked again every
   millisecond, at most this many times. Its device record is this long, with the owner at this place. */
#define PAD_MBUS_NO_DEVICE ((int32_t)0x809b0005)
#define PAD_SEAT_TRIES 30
#define PAD_INFO_SIZE 0x100u
#define PAD_INFO_OWNER 0xC8u
/* bind: seats a device in a user. info: the device's record. pause: a millisecond. Each call answers 0 or the console's code. */
struct pad_mbus{int32_t(*bind)(uint64_t device,int32_t user);int32_t(*info)(uint64_t device,void*record,uint32_t size);void(*pause)(void);};
/* Seats controller handle in user: 0 when the console then names that user as its owner. owner: who it names (0 if unread). */
static int32_t pad_seat(const struct pad_mbus*m,int handle,uint32_t user,uint32_t*owner,int*tries){
 int32_t rv;int n=0;*owner=0;
 do{if(n)m->pause();rv=m->bind((uint64_t)(uint32_t)handle,(int32_t)user);n++;}while(rv==PAD_MBUS_NO_DEVICE&&n<PAD_SEAT_TRIES);
 *tries=n;if(rv)return rv;
 unsigned char record[PAD_INFO_SIZE];for(size_t i=0;i<sizeof record;i++)record[i]=0;
 int32_t got=m->info((uint64_t)(uint32_t)handle,record,PAD_INFO_SIZE);if(got)return got;
 memcpy(owner,record+PAD_INFO_OWNER,4);return *owner==user?0:PAD_SEAT_OTHER;
}
/* While starting, the error is the step under way, so a start that never comes back still says where it stopped. A system call that
   failed is 'PE' and its errno. */
#define PAD_STEP(n) ((int32_t)(0x50530000u|(uint32_t)(n)))
#define PAD_ERRNO(e) ((int32_t)(0x50450000u|((uint32_t)(e)&0xffffu)))
enum{PAD_STEP_USER=1,PAD_STEP_FOREGROUND=2,PAD_STEP_OPEN=3,PAD_STEP_LEFTOVERS=4,PAD_STEP_ADD=5,PAD_STEP_FIRST_STATE=6,PAD_STEP_SEAT=7};
/* All in microseconds. Silence this long lets go of a controller's buttons. A sender is answered at least this often. Starting may take
   this long before it counts as failed. After this much silence any sequence is taken, because the PC was restarted. A controller the
   console refused is asked for again after this long. A sender quiet this long loses its controller. Once failed, the companion ends after
   this much silence or this long in all. With no sender for this long, it ends. Opening /dev/hid takes milliseconds; the limit is
   generous so that a slow console is not taken for a stuck one. */
#define PAD_QUIET_US 250000ull
#define PAD_ANSWER_US 100000ull
#define PAD_START_LIMIT_US 8000000ull
#define PAD_RESTART_US 1000000ull
#define PAD_RETRY_US 2000000ull
#define PAD_GONE_US 90000000ull
#define PAD_FAILED_QUIET_US 10000000ull
#define PAD_FAILED_LIMIT_US 30000000ull
#define PAD_IDLE_US 600000000ull
/* How long the companion waits with no controller in use: the usual ten minutes, or the away hours (away-rules.h). */
static uint64_t pad_idle_us=PAD_IDLE_US;
#define PAD_POLL_MS 50
/* The console side, given to the loop so the PC tests can stand in for it.
   receive: a packet's size and who sent it (an address and port in one number), 0 when none came in time, below 0 when the socket broke.
   answer: a packet to one sender. progress: the start-up thread's state and error; once READY, /dev/hid is open for this user.
   add: a new controller, 0 with its handle or an error. insert: one state for a controller, 0 when the console took it. remove: the
   controller goes. seat: a controller just added is seated in the user in front, 0 when it is theirs. add, insert, remove and seat are
   only called once ready. */
struct pad_calls{
 int(*receive)(unsigned char*w,size_t cap,int timeout_ms,uint64_t*sender);
 void(*answer)(uint64_t sender,const unsigned char*w,size_t n);
 uint64_t(*now)(void);
 int(*progress)(int32_t*error);
 int32_t(*add)(int*handle);
 int32_t(*insert)(int handle,const unsigned char*record);
 int32_t(*remove)(int handle);
 int32_t(*seat)(int handle);
};
struct pad_report{uint32_t packets,inserted,neutral,answers,ignored,insert_failed,added,removed,refused,seated,seat_failed;int32_t first_insert_error,first_seat_error;};
enum{PAD_END_IDLE=1,PAD_END_FAILED=2,PAD_END_SOCKET=3};
/* One sender's controller. handle is below 0 while it has none; error is the console's answer to its add, or to its last state. */
struct pad_slot{uint64_t sender,heard,answered,tried;uint32_t last;int used,seen,held,told,asked,handle,seated;int32_t error;};
static const unsigned char pad_centred[6]={0x80,0x80,0x80,0x80,0,0};
static void pad_put(const struct pad_calls*c,struct pad_report*r,struct pad_slot*s,uint32_t buttons,const unsigned char*sticks){
 unsigned char record[PAD_BLOCK_SIZE];fill_pad_state(record,buttons,sticks);int32_t rv=c->insert(s->handle,record);
 if(rv){if(!r->insert_failed)r->first_insert_error=rv;r->insert_failed++;}
 s->error=rv;
}
/* Lets go of everything, then removes the controller and frees the place. */
static void pad_drop(const struct pad_calls*c,struct pad_report*r,struct pad_slot*s){
 if(s->handle>=0){if(s->held){pad_put(c,r,s,0,pad_centred);r->neutral++;}c->remove(s->handle);r->removed++;}
 memset(s,0,sizeof*s);s->handle=-1;
}
static struct pad_slot*pad_find(struct pad_slot*slots,uint64_t sender){for(int i=0;i<PAD_SLOTS;i++)if(slots[i].used&&slots[i].sender==sender)return&slots[i];return 0;}
static int pad_live(const struct pad_slot*slots){int n=0;for(int i=0;i<PAD_SLOTS;i++)n+=slots[i].used;return n;}
static int pad_any_seated(const struct pad_slot*slots){for(int i=0;i<PAD_SLOTS;i++)if(slots[i].used&&slots[i].seated)return 1;return 0;}
/* Takes the senders' packets, answers them and hands them to the console, until no controller has been in use for the idle time or
   starting failed. It never waits on the start-up: that runs on its own thread, and senders are answered "starting" meanwhile and
   "failed" once it takes too long. */
static int pad_run(const struct pad_calls*c,struct pad_report*r){
 unsigned char wire[64],status[PAD_STATUS_SIZE],sticks[6];struct pad_slot slots[PAD_SLOTS];
 for(int i=0;i<PAD_SLOTS;i++){memset(&slots[i],0,sizeof slots[i]);slots[i].handle=-1;}
 uint64_t began=c->now(),heard=began,failed_at=0,sender=0;uint32_t sequence=0,buttons=0;int failed=0;
 for(;;){
  int n=c->receive(wire,sizeof wire,PAD_POLL_MS,&sender);uint64_t now=c->now();
  if(n<0){for(int i=0;i<PAD_SLOTS;i++)if(slots[i].used)pad_drop(c,r,&slots[i]);return PAD_END_SOCKET;}
  int32_t error=0;int state=c->progress(&error);
  if(state==PAD_STARTING&&now-began>=PAD_START_LIMIT_US){state=PAD_FAILED;error=PAD_START_HUNG;}
  if(state==PAD_FAILED&&!failed){failed=1;failed_at=now;}
  /* A start-up that comes back late still counts. */
  if(state==PAD_READY)failed=0;
  struct pad_slot*s=n>0?pad_find(slots,sender):0;
  if(n>0&&is_pad_probe(wire,(size_t)n)){pad_status_wire(status,(uint32_t)state,error,0,0);c->answer(sender,status,PAD_STATUS_SIZE);r->answers++;}
  else if(n>0&&is_pad_quit(wire,(size_t)n)){
   /* Only that sender's controller goes. The companion stays for the next press, which then plays at once, and ends after the
      usual idle time with no controller in use. */
   heard=now;
   if(s)pad_drop(c,r,s);
  }else if(n>0&&read_pad_wire(wire,(size_t)n,&sequence,&buttons,sticks)){
   r->packets++;heard=now;
   if(!s)for(int i=0;i<PAD_SLOTS&&!s;i++)if(!slots[i].used){s=&slots[i];memset(s,0,sizeof*s);s->used=1;s->sender=sender;s->handle=-1;s->told=-1;}
   if(!s){pad_status_wire(status,PAD_FAILED,PAD_FULL,sequence,0);c->answer(sender,status,PAD_STATUS_SIZE);r->answers++;}
   else{
    int fresh=!s->seen||now-s->heard>=PAD_RESTART_US||newer_sequence(sequence,s->last);s->heard=now;
    if(fresh){s->seen=1;s->last=sequence;}else r->ignored++;
    /* Its controller is made with its first state once ready; one the console refused is asked for again a little later. */
    if(state==PAD_READY&&s->handle<0&&(!s->asked||now-s->tried>=PAD_RETRY_US)){
     int handle=-1;s->asked=1;s->tried=now;int32_t rv=c->add(&handle);
     if(!rv&&handle<0)rv=PAD_NO_DEVICE;
     if(rv){s->error=rv;r->refused++;}else{s->handle=handle;s->error=0;r->added++;fresh=1;
      /* The user in front's controller, while no other controller here is theirs; the others are other players. A seat that fails
         leaves a controller that still plays once the PS5's question is answered. */
      if(!pad_any_seated(slots)){int32_t seat=c->seat(handle);if(!seat){s->seated=1;r->seated++;}else{if(!r->seat_failed)r->first_seat_error=seat;r->seat_failed++;}}
     }
    }
    if(fresh&&state==PAD_READY&&s->handle>=0){pad_put(c,r,s,buttons,sticks);s->held=1;r->inserted++;}
    /* Once ready, the error is the console's answer to this sender's controller: 0 when it took the last state. */
    int mine=state==PAD_READY?(s->handle>=0?PAD_READY:PAD_FAILED):state;int32_t said=state==PAD_READY?s->error:error;
    if(mine!=s->told||now-s->answered>=PAD_ANSWER_US){
     pad_status_wire(status,(uint32_t)mine,said,s->last,s->handle>=0?(uint32_t)(s-slots)+1:0);c->answer(sender,status,PAD_STATUS_SIZE);s->told=mine;s->answered=now;r->answers++;
    }
   }
  }
  /* A sender sends all the time while its controller is in use, so silence means it is gone: no button may stay held, and after a
     longer silence its controller goes. */
  for(int i=0;i<PAD_SLOTS;i++){
   struct pad_slot*q=&slots[i];if(!q->used)continue;
   if(q->held&&q->handle>=0&&now-q->heard>=PAD_QUIET_US){pad_put(c,r,q,0,pad_centred);q->held=0;r->neutral++;}
   if(now-q->heard>=PAD_GONE_US)pad_drop(c,r,q);
  }
  if(failed){uint64_t since=heard>failed_at?heard:failed_at;if(now-since>=PAD_FAILED_QUIET_US||now-failed_at>=PAD_FAILED_LIMIT_US)break;}
  if(!pad_live(slots)&&now-heard>=pad_idle_us)break;
 }
 for(int i=0;i<PAD_SLOTS;i++)if(slots[i].used)pad_drop(c,r,&slots[i]);
 return failed?PAD_END_FAILED:PAD_END_IDLE;
}
