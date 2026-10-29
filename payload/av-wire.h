/* Packet framing: no demux probe or unbounded presentation queue. */
static int tables(void){return 0;}
static int pes(int pid,int id,const unsigned char*data,size_t n,uint64_t pts,uint64_t dts,int video){(void)pid;(void)id;unsigned char h[32]={0};memcpy(h,"PSAV",4);h[4]=1;h[5]=video?1:2;uint32_t size=(uint32_t)n;memcpy(h+8,&size,4);memcpy(h+12,&pts,8);memcpy(h+20,&dts,8);return send_all(h,32)||send_all(data,n)?-1:0;}
static uint64_t get64(const unsigned char*p,int off){uint64_t v;memcpy(&v,p+off,8);return v;}
static uint64_t mono_us(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000+t.tv_nsec/1000;}
