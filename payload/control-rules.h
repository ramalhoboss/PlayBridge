/* What the control port accepts. No console calls here, so the PC tests run this file directly. */
#define CONTROL_PORT 9077
enum{CONTROL_STATUS=1,CONTROL_FILE=2,CONTROL_LAUNCH=3,CONTROL_CLOSE=4,CONTROL_REST=6,CONTROL_POWER_OFF=7,CONTROL_REBOOT=8,CONTROL_LIST=9,CONTROL_RANGE=10,CONTROL_FAN=11};
#define CONTROL_BODY_MAX 128u
/* The most one request for part of a file returns. */
#define CONTROL_RANGE_MAX 0x100000u
static int same_text(const char*a,size_t n,const char*b){size_t i=0;for(;i<n&&b[i];i++)if(a[i]!=b[i])return 0;return i==n&&!b[i];}
static size_t skip_text(const char*a,size_t n,const char*b){size_t i=0;for(;b[i];i++)if(i>=n||a[i]!=b[i])return 0;return i;}
static int valid_title(const char*t,size_t n){
 if(n!=9)return 0;
 for(size_t i=0;i<9;i++)if(i<4?t[i]<'A'||t[i]>'Z':t[i]<'0'||t[i]>'9')return 0;
 return 1;
}
/* A trophy set as the console names its folders: NPWR, five digits, an underscore and two digits. */
static int valid_trophy_set(const char*t,size_t n){
 if(n!=12||t[0]!='N'||t[1]!='P'||t[2]!='W'||t[3]!='R'||t[9]!='_')return 0;
 for(size_t i=4;i<12;i++)if(i!=9&&(t[i]<'0'||t[i]>'9'))return 0;
 return 1;
}
/* A user's own folder: the user id as eight lowercase hexadecimal digits. */
static int valid_user_folder(const char*t,size_t n){
 if(n!=8)return 0;
 for(size_t i=0;i<8;i++)if(!((t[i]>='0'&&t[i]<='9')||(t[i]>='a'&&t[i]<='f')))return 0;
 return 1;
}
/* Where the console keeps its own screenshots and video clips, on its storage and on extended storage. */
static const char*const capture_roots[]={"/user/av_contents/","/mnt/ext0/user/av_contents/","/mnt/ext1/user/av_contents/",0};
/* A path with nothing in it that could climb out of its root: no control characters, backslashes, empty, . or .. parts. */
static int plain_path(const char*p,size_t n){
 if(!n||p[0]!='/')return 0;
 for(size_t i=0;i<n;i++){
  if((unsigned char)p[i]<0x20||p[i]=='\\'||p[i]==127)return 0;
  if(p[i]=='/'){
   size_t j=i+1;while(j<n&&p[j]!='/')j++;
   size_t part=j-i-1;
   if(j<n&&part==0)return 0;
   if((part==1&&p[i+1]=='.')||(part==2&&p[i+1]=='.'&&p[i+2]=='.'))return 0;
  }
 }
 return 1;
}
static size_t capture_root(const char*p,size_t n){
 for(int i=0;capture_roots[i];i++){size_t at=skip_text(p,n,capture_roots[i]);if(at)return at;}
 return 0;
}
/* A user's saves: PS5 games' under savedata_prospero and PS4 games' under savedata, each game in a folder named by its title id.
   Where the user's save folder ends in the path, or 0. */
static size_t save_root(const char*p,size_t n){
 static const char*const kinds[]={"/savedata_prospero","/savedata",0};
 size_t at=skip_text(p,n,"/user/home/");
 if(!at||n<at+8||!valid_user_folder(p+at,8))return 0;
 at+=8;
 for(int i=0;kinds[i];i++){size_t inner=skip_text(p+at,n-at,kinds[i]);if(inner&&(at+inner==n||p[at+inner]=='/'))return at+inner;}
 return 0;
}
/* A folder of saves that may be listed: the user's save folder, a game's own folder in it, or any folder below that one. */
static int save_folder(const char*p,size_t n){
 if(!plain_path(p,n)||p[n-1]=='/')return 0;
 size_t root=save_root(p,n);if(!root)return 0;
 if(root==n)return 1;
 return n>=root+10&&valid_title(p+root+1,9)&&(n==root+10||p[root+10]=='/');
}
/* A file inside a game's own save folder, and not a hidden one. Only read: nothing on this port writes to the console. */
static int save_file(const char*p,size_t n){
 if(!plain_path(p,n)||p[n-1]=='/')return 0;
 size_t root=save_root(p,n);
 if(!root||n<root+12||!valid_title(p+root+1,9)||p[root+10]!='/')return 0;
 size_t last=n;while(last&&p[last-1]!='/')last--;
 return last<n&&p[last]!='.';
}
/* A folder that may be listed: a capture root itself, or any folder inside one, and the user's saves. */
static int allowed_folder(const char*path,size_t n){
 if(!plain_path(path,n))return 0;
 if(save_folder(path,n))return 1;
 for(int i=0;capture_roots[i];i++){size_t root=0;while(capture_roots[i][root])root++;if(n!=root-1)continue;size_t k=0;while(k<n&&path[k]==capture_roots[i][k])k++;if(k==n)return 1;}
 return capture_root(path,n)!=0&&path[n-1]!='/';
}
/* A screenshot or a clip inside a capture root, by its ending. */
static int capture_file(const char*path,size_t n){
 static const char*const endings[]={".jpg",".jpeg",".png",".webp",".mp4",".webm",0};
 if(!plain_path(path,n)||!capture_root(path,n))return 0;
 /* Not a hidden file: its name must not start with a dot. */
 size_t last=n;while(last&&path[last-1]!='/')last--;
 if(last==n||path[last]=='.')return 0;
 for(int i=0;endings[i];i++){
  size_t e=0;while(endings[i][e])e++;
  if(n<=e)continue;
  int same=1;for(size_t k=0;k<e;k++){char c=path[n-e+k];if(c>='A'&&c<='Z')c=(char)(c-'A'+'a');if(c!=endings[i][k]){same=0;break;}}
  if(same)return 1;
 }
 return 0;
}
/* A game's trophies: the set's own file, with each trophy's name and grade, and the user's record of which they have and when. */
static int trophy_file(const char*path,size_t n){
 size_t at=skip_text(path,n,"/user/trophy2/nobackup/conf/");
 if(at)return n>=at+12&&valid_trophy_set(path+at,12)&&same_text(path+at+12,n-at-12,"/TROPHY.UCP");
 at=skip_text(path,n,"/user/home/");
 if(!at||n<at+8||!valid_user_folder(path+at,8))return 0;
 at+=8;size_t inner=skip_text(path+at,n-at,"/trophy2/nobackup/data/");
 if(!inner)return 0;
 at+=inner;return n>=at+12&&valid_trophy_set(path+at,12)&&same_text(path+at+12,n-at-12,"/TRPTITLE.DAT");
}
/* The game database, each game's own picture, background art, music and trophy files, the user's saves and the payloads' logs. Nothing else on the console can be read through this port. */
static int allowed_file(const char*path,size_t n){
 static const char*const exact[]={"/system_data/priv/mms/app.db","/system_data/priv/mms/app.db-wal","/data/playbridge-control.txt","/data/playbridge-control.old.txt","/data/ps5screen-av3.txt","/data/playbridge-pad.txt","/data/playbridge-pad.old.txt",0};
 /* Where a game keeps them, before and after its title id. */
 static const char*const roots[][2]={{"/user/appmeta/external/",""},{"/user/appmeta/",""},{"/user/catalog_downloader/appmeta/",""},{"/mnt/ext0/user/appmeta/",""},{"/mnt/ext1/user/appmeta/",""},{"/user/app/","/sce_sys"},{"/mnt/ext0/user/app/","/sce_sys"},{"/mnt/ext1/user/app/","/sce_sys"},{0,0}};
 static const char*const names[]={"/icon0.png","/pic0.dds","/pic0.png","/snd0.at9","/trophy2/npbind.dat",0};
 for(int i=0;exact[i];i++)if(same_text(path,n,exact[i]))return 1;
 if(capture_file(path,n)||trophy_file(path,n)||save_file(path,n))return 1;
 for(int i=0;roots[i][0];i++){
  size_t at=skip_text(path,n,roots[i][0]);
  if(!at||n<at+9||!valid_title(path+at,9))continue;
  at+=9;
  if(roots[i][1][0]){size_t inner=skip_text(path+at,n-at,roots[i][1]);if(!inner)continue;at+=inner;}
  for(int j=0;names[j];j++)if(same_text(path+at,n-at,names[j]))return 1;
 }
 return 0;
}
/* The PS5 keeps its own automatic fan control, which holds the console at a target temperature; /dev/icc_fan reads and sets that
   target. The device, its two requests and where the target sits were found by ShadowMountPlus (GPL-3); the code here is our own. */
#define FAN_DEVICE "/dev/icc_fan"
#define FAN_GET 0xC01C8F08UL
#define FAN_SET 0xC01C8F07UL
#define FAN_BLOCK 28u
#define FAN_SELECTOR_AT 2u
#define FAN_TARGET_AT 5u
#define FAN_LOWEST 50
#define FAN_HIGHEST 91
/* A target PlayBridge may set: never warmer than the console's own, never below the lowest the fan control takes. 0 asks for the
   console's own back. */
static int fan_target_allowed(int want,int own){
 if(want==0)return 1;
 return own>=FAN_LOWEST&&own<=FAN_HIGHEST&&want>=FAN_LOWEST&&want<=own;
}
/* After a reading of the target: own is the console's own target, set PlayBridge's while it is in place, else 0. A target that is not
   PlayBridge's was chosen by the console, as it may be when a game starts, so it becomes the console's own. */
static void fan_follow(int now,int*own,int*set){
 if(now<=0||(*set&&now==*set))return;
 *own=now;*set=0;
}
/* The note left on the console while a target of PlayBridge's is in place: "own set", so a payload loaded again tells the console's own
   target apart from PlayBridge's. 1 when the text is such a note. */
static int fan_note(const char*text,size_t n,int*own,int*set){
 int v[2]={0,0};size_t i=0;
 for(int k=0;k<2;k++){
  if(k){if(i>=n||text[i]!=' ')return 0;i++;}
  size_t start=i;while(i<n&&i-start<3&&text[i]>='0'&&text[i]<='9'){v[k]=v[k]*10+(text[i]-'0');i++;}
  if(i==start)return 0;
 }
 while(i<n&&(text[i]=='\n'||text[i]=='\r'))i++;
 if(i!=n||v[1]==0||v[1]==v[0]||!fan_target_allowed(v[1],v[0]))return 0;
 *own=v[0];*set=v[1];return 1;
}
/* A request for part of a file: where it starts and how much, then the path. The path must be one the port may read. */
static int range_request(const char*body,size_t n,uint64_t*offset,uint32_t*length){
 if(n<=12)return 0;
 memcpy(offset,body,8);memcpy(length,body+8,4);
 return *length>0&&*length<=CONTROL_RANGE_MAX&&allowed_file(body+12,n-12);
}
/* The running game's frame count, from the display controller. The display driver counts the pictures it shows, and the PC divides the
   change between two readings by the time between them. The request and its three numbers (selector, mask, where the count sits) were
   found by porhe911 (Common FPS for PS5) and are read the same way by ps5upload; the code here is our own. Without a game the request
   fails with ENOENT. */
#define FPS_DEVICE "/dev/dce"
#define FPS_REQUEST 0x80308217ULL
/* The same request sign-extended, which some firmware wants: tried once when the first is refused as invalid. */
#define FPS_REQUEST_WIDE 0xFFFFFFFF80308217ULL
#define FPS_SELECTOR 0x10000000AULL
#define FPS_MASK 0x8000000000ULL
#define FPS_COUNT_AT 8u
/* The kernel wrote 128 bytes where this was measured. The block is far larger and the console side puts a page nobody may touch after
   it, so a kernel that writes more fails the copy instead of writing over the payload. */
#define FPS_BLOCK 0x4000u
#define FPS_MARK 0xA5
enum{FPS_OK=0,FPS_NO_GAME=1,FPS_NO_DEVICE=2,FPS_FAILED=3};
struct fps_request{uint64_t selector,mask,output,reserved[3];};
_Static_assert(sizeof(struct fps_request)==0x30,"the request carries 48 bytes");
/* One reading into block. request sends the ioctl and returns 0 or the error number. Fills count only for FPS_OK; error is the
   request's own answer. The block is marked first, so the bytes the kernel wrote can be told from the rest. */
static int fps_read(int(*request)(uint64_t,struct fps_request*),unsigned char*block,uint64_t*count,int*error){
 struct fps_request arg={FPS_SELECTOR,FPS_MASK,(uint64_t)(uintptr_t)block,{0,0,0}};
 for(uint32_t i=0;i<FPS_BLOCK;i++)block[i]=FPS_MARK;
 int e=request(FPS_REQUEST,&arg);
 if(e==EINVAL){for(uint32_t i=0;i<FPS_BLOCK;i++)block[i]=FPS_MARK;e=request(FPS_REQUEST_WIDE,&arg);}
 *error=e;
 if(e)return e==ENOENT?FPS_NO_GAME:FPS_FAILED;
 /* What the kernel wrote: everything before the trailing marker bytes. A count that happens to end in them only looks shorter. */
 uint32_t n=FPS_BLOCK;while(n&&block[n-1]==FPS_MARK)n--;
 if(n<FPS_COUNT_AT+8)return FPS_FAILED;
 memcpy(count,block+FPS_COUNT_AT,8);return FPS_OK;
}
/* The console's temperatures. Each getter fills one int, in degrees Celsius, and returns 0 when it read the sensor. A reading is only sent when the
   getter says so and the number fits a real sensor (1 to 150 degrees, the bounds ps5upload uses); otherwise the PC gets NO_READING.
   The power getter writes a 112-byte block (power_parts below). It once got 16 bytes here, and the rest landed on the temperatures
   beside it on the stack, which is where the CPU reading of 994 came from. */
#define TEMPERATURE_MIN_C 1
#define TEMPERATURE_MAX_C 150
#define NO_READING (-1)
static int temperature_reading(int result,int value){return result==0&&value>=TEMPERATURE_MIN_C&&value<=TEMPERATURE_MAX_C?value:NO_READING;}
/* The chip's power. sceKernelGetSocPowerConsumption fills a block of 112 bytes: 8 rails of {power mW, voltage mV, current mA} as 32-bit
   numbers, then other data. Rails 0-1 feed the GPU, 2-3 the CPU and the rest of the chip, 4-7 the GDDR6 memory (ps5upload's notes,
   phantomptr; the code here is our own). The block given to it is far larger than it writes, so nothing beside it can be reached.
   parts gets the GPU's, the CPU's and the memory's milliwatts, or NO_READING in all three when the getter failed or a number cannot
   be a rail's (one rail over 200 W, or all of them together over 500 W or at nothing). */
#define POWER_BLOCK 0x100u
#define POWER_RAILS 8u
#define POWER_RAIL_BYTES 12u
#define POWER_RAIL_MAX_MW 200000u
#define POWER_TOTAL_MAX_MW 500000u
static int power_parts(int result,const unsigned char*block,int parts[3]){
 parts[0]=parts[1]=parts[2]=NO_READING;
 if(result!=0)return 0;
 uint32_t sums[3]={0,0,0},total=0;
 for(uint32_t rail=0;rail<POWER_RAILS;rail++){
  uint32_t mw;memcpy(&mw,block+rail*POWER_RAIL_BYTES,4);
  if(mw>POWER_RAIL_MAX_MW)return 0;
  sums[rail<2?0:rail<4?1:2]+=mw;total+=mw;
 }
 if(!total||total>POWER_TOTAL_MAX_MW)return 0;
 for(int i=0;i<3;i++)parts[i]=(int)sums[i];
 return 1;
}
