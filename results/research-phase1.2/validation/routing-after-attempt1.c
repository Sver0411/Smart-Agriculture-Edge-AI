#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
static char owner[3]="A1"; static int link_retry;
typedef struct { int used; } rx_buffer_t;
static size_t strlcpy(char *d,const char *s,size_t n) { size_t z=strlen(s);if(n){size_t k=z<n-1?z:n-1;memcpy(d,s,k);d[k]=0;}return z; }
static int connect_gateway(const char *s) { return !strcmp(s,"A1")?11:22; }
static void close(int fd) {(void)fd;}
static uint64_t uptime_ms(void) {return 0;}
static void b1_link_failed(int *r,uint64_t t) {(void)r;(void)t;}
enum {B1_REG_ACCEPTED,B1_REG_NOT_OWNER};static int register_node(int f,const char *s,rx_buffer_t *r){(void)f;(void)r;return !strcmp(s,"A2")?B1_REG_ACCEPTED:B1_REG_NOT_OWNER;}
int main(void){int chosen=-1;for(int round=0;round<1;++round){
        char candidate[3], preferred[3];
        memcpy(preferred,owner,3);
        int fd=-1;
        rx_buffer_t rx={0};
        /* Each candidate is tried at most once per bounded connection round.
         * Successful TCP connect does not imply accepted registration. */
        for (int attempt=0;attempt<2;++attempt) {
            const char *name=attempt==0 ? preferred : (!strcmp(preferred,"A1") ? "A2" : "A1");
            memcpy(candidate,name,3);
            fd=connect_gateway(candidate);
            if (fd<0) continue;
            memset(&rx,0,sizeof(rx));
            if (register_node(fd,candidate,&rx)==B1_REG_ACCEPTED) break;
            close(fd);fd=-1;
        }
        if (fd<0) { b1_link_failed(&link_retry,uptime_ms());continue; }
chosen=fd;break;}
assert(chosen==22);puts("A1 TCP accepted / registration rejected -> A2 registered PASS");}
