/* What the controller companion accepts, what it answers and when it gives up. The companion runs as its own process on its own port, so
   nothing it waits for can hold the video, the control port or the capture. No console calls here, so the PC tests run this file directly. */
#define PAD_PORT 9078
/* One controller state from the PC. Sticks and triggers use the console's own 0-255 ranges. */
#define PAD_WIRE_SIZE 20u
#define PAD_BUTTONS 0x0011fffeu
static int read_pad_wire(const unsigned char*w,size_t n,uint32_t*sequence,uint32_t*buttons,unsigned char*sticks){
 if(n!=PAD_WIRE_SIZE||w[0]!='P'||w[1]!='B'||w[2]!='P'||w[3]!='1')return 0;
 memcpy(sequence,w+4,4);memcpy(buttons,w+8,4);*buttons&=PAD_BUTTONS;memcpy(sticks,w+12,6);return 1;
}
/* A later sequence number, allowing for wrap-around. UDP can reorder, and an old state must not undo a newer one. */
static int newer_sequence(uint32_t now,uint32_t last){return (int32_t)(now-last)>0;}
/* The pad record scePadVirtualDeviceInsertData reads: buttons, sticks, triggers, then a resting orientation and connected. */
#define PAD_DATA_SIZE 0x100u
static void fill_pad_data(unsigned char*d,uint32_t buttons,const unsigned char*sticks,uint64_t timestamp){
 static const unsigned char level[16]={0,0,0,0,0,0,0,0,0,0,0,0,0,0,0x80,0x3f};
 for(size_t i=0;i<PAD_DATA_SIZE;i++)d[i]=0;
 memcpy(d,&buttons,4);memcpy(d+4,sticks,6);memcpy(d+0xc,level,16);d[0x4c]=1;memcpy(d+0x50,&timestamp,8);
}
/* The answer to the PC: 'PBS1', where the controller stands, an error code and the newest sequence taken. The PC never waits for it. */
#define PAD_STATUS_SIZE 16u
enum{PAD_STARTING=0,PAD_READY=1,PAD_FAILED=2};
static void pad_status_wire(unsigned char*w,uint32_t state,int32_t error,uint32_t sequence){
 memcpy(w,"PBS1",4);memcpy(w+4,&state,4);memcpy(w+8,&error,4);memcpy(w+12,&sequence,4);
}
/* Errors of the companion's own, beside the console's 8xxxxxxx codes: 'PB' then a number. */
#define PAD_MISSING ((int32_t)0x50420001)   /* libScePad or one of its calls was not found */
#define PAD_NO_USER ((int32_t)0x50420002)   /* nobody is signed in on the console */
#define PAD_NO_DEVICE ((int32_t)0x50420003) /* the console added no controller */
#define PAD_START_HUNG ((int32_t)0x50420004)/* starting the controller did not come back in time */
/* All in microseconds. Silence this long lets go of every button. The PC is answered at least this often. Starting may take this long
   before it counts as failed. After this much silence any sequence is taken, because the PC was restarted. Once failed, the companion
   ends after this much silence or this long in all. With no PC for this long, it ends. The start-up limit is above the 5 s that
   scePadInit's Mbus connection spends on its own retries (50 tries, 100 ms apart, on firmware 13.60), so a refusal there comes back
   with its own code instead of being taken for a hang. */
#define PAD_QUIET_US 250000ull
#define PAD_ANSWER_US 100000ull
#define PAD_START_LIMIT_US 8000000ull
#define PAD_RESTART_US 1000000ull
#define PAD_FAILED_QUIET_US 10000000ull
#define PAD_FAILED_LIMIT_US 30000000ull
#define PAD_IDLE_US 600000000ull
#define PAD_POLL_MS 50
/* The console side, given to the loop so the PC tests can stand in for it. receive gives a packet's size, 0 when none came in time, or
   below 0 when the socket broke; answer goes to whoever sent the last packet; progress is the start-up thread's state and error; insert
   is only called once the controller is ready. */
struct pad_calls{
 int(*receive)(unsigned char*w,size_t cap,int timeout_ms);
 void(*answer)(const unsigned char*w,size_t n);
 uint64_t(*now)(void);
 int(*progress)(int32_t*error);
 int(*insert)(const unsigned char*record);
};
struct pad_report{uint32_t packets,inserted,neutral,answers,ignored,insert_failed;int32_t first_insert_error;};
enum{PAD_END_IDLE=1,PAD_END_FAILED=2,PAD_END_SOCKET=3};
static int pad_put(const struct pad_calls*c,struct pad_report*r,unsigned char*record,uint32_t buttons,const unsigned char*sticks,uint64_t now){
 fill_pad_data(record,buttons,sticks,now);int rv=c->insert(record);
 if(rv<0){if(!r->insert_failed)r->first_insert_error=rv;r->insert_failed++;}
 return rv;
}
/* Takes the PC's packets, answers them and hands them to the console, until the PC has gone or starting failed. It never waits on the
   console: start-up runs on its own thread, and the PC is answered "starting" meanwhile and "failed" once it takes too long. */
static int pad_run(const struct pad_calls*c,struct pad_report*r){
 static const unsigned char centred[6]={0x80,0x80,0x80,0x80,0,0};
 unsigned char wire[64],record[PAD_DATA_SIZE],status[PAD_STATUS_SIZE],sticks[6];
 uint64_t began=c->now(),heard=began,answered=0,failed_at=0;uint32_t sequence=0,buttons=0,last=0;int seen=0,held=0,told=-1,failed=0;int32_t refused=0;
 for(;;){
  int n=c->receive(wire,sizeof wire,PAD_POLL_MS);uint64_t now=c->now();
  if(n<0)return PAD_END_SOCKET;
  int32_t error=0;int state=c->progress(&error);
  if(state==PAD_STARTING&&now-began>=PAD_START_LIMIT_US){state=PAD_FAILED;error=PAD_START_HUNG;}
  if(state==PAD_FAILED&&!failed){failed=1;failed_at=now;}
  /* A start-up that comes back late still counts. */
  if(state==PAD_READY)failed=0;
  if(n>0&&read_pad_wire(wire,(size_t)n,&sequence,&buttons,sticks)){
   r->packets++;
   int fresh=!seen||now-heard>=PAD_RESTART_US||newer_sequence(sequence,last);heard=now;
   if(fresh){
    seen=1;last=sequence;
    if(state==PAD_READY){int rv=pad_put(c,r,record,buttons,sticks,now);refused=rv<0?rv:0;held=1;r->inserted++;}
   }else r->ignored++;
   /* Once ready, the error is the console's answer to the last state handed over, 0 when it took it. */
   if(state!=told||now-answered>=PAD_ANSWER_US){pad_status_wire(status,(uint32_t)state,state==PAD_READY?refused:error,last);c->answer(status,PAD_STATUS_SIZE);told=state;answered=now;r->answers++;}
  }
  /* The PC sends all the time while a controller is in use, so silence means it is gone: no button may stay held. */
  if(held&&state==PAD_READY&&now-heard>=PAD_QUIET_US){pad_put(c,r,record,0,centred,now);held=0;r->neutral++;}
  if(failed){uint64_t since=heard>failed_at?heard:failed_at;if(now-since>=PAD_FAILED_QUIET_US||now-failed_at>=PAD_FAILED_LIMIT_US)return PAD_END_FAILED;}
  if(now-heard>=PAD_IDLE_US)return PAD_END_IDLE;
 }
}
