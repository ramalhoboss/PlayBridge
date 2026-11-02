/* What the control and controller ports accept. No console calls here, so the PC tests run this file directly. */
#define CONTROL_PORT 9077
#define PAD_PORT 9078
enum{CONTROL_STATUS=1,CONTROL_FILE=2,CONTROL_LAUNCH=3,CONTROL_CLOSE=4,CONTROL_REST=6,CONTROL_POWER_OFF=7,CONTROL_REBOOT=8};
#define CONTROL_BODY_MAX 128u
static int same_text(const char*a,size_t n,const char*b){size_t i=0;for(;i<n&&b[i];i++)if(a[i]!=b[i])return 0;return i==n&&!b[i];}
static size_t skip_text(const char*a,size_t n,const char*b){size_t i=0;for(;b[i];i++)if(i>=n||a[i]!=b[i])return 0;return i;}
static int valid_title(const char*t,size_t n){
 if(n!=9)return 0;
 for(size_t i=0;i<9;i++)if(i<4?t[i]<'A'||t[i]>'Z':t[i]<'0'||t[i]>'9')return 0;
 return 1;
}
/* The game database, each game's own picture, background art and music, and this payload's logs. Nothing else on the console can be read through this port. */
static int allowed_file(const char*path,size_t n){
 static const char*const exact[]={"/system_data/priv/mms/app.db","/system_data/priv/mms/app.db-wal","/data/playbridge-control.txt","/data/playbridge-control.old.txt","/data/ps5screen-av3.txt",0};
 /* Where a game keeps them, before and after its title id. */
 static const char*const roots[][2]={{"/user/appmeta/external/",""},{"/user/appmeta/",""},{"/user/catalog_downloader/appmeta/",""},{"/mnt/ext0/user/appmeta/",""},{"/mnt/ext1/user/appmeta/",""},{"/user/app/","/sce_sys"},{"/mnt/ext0/user/app/","/sce_sys"},{"/mnt/ext1/user/app/","/sce_sys"},{0,0}};
 static const char*const names[]={"/icon0.png","/pic0.dds","/pic0.png","/snd0.at9",0};
 for(int i=0;exact[i];i++)if(same_text(path,n,exact[i]))return 1;
 for(int i=0;roots[i][0];i++){
  size_t at=skip_text(path,n,roots[i][0]);
  if(!at||n<at+9||!valid_title(path+at,9))continue;
  at+=9;
  if(roots[i][1][0]){size_t inner=skip_text(path+at,n-at,roots[i][1]);if(!inner)continue;at+=inner;}
  for(int j=0;names[j];j++)if(same_text(path+at,n-at,names[j]))return 1;
 }
 return 0;
}
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
