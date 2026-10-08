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
static bool register_node(int f,const char *s,rx_buffer_t *r){(void)f;(void)r;return !strcmp(s,"A2");}
int main(void){int chosen=-1;for(int round=0;round<1;++round){
        char candidate[3];
        strlcpy(candidate, owner, sizeof(candidate));
        int fd = connect_gateway(candidate);
        if (fd < 0) {
            strlcpy(candidate, strcmp(owner, "A1") == 0 ? "A2" : "A1", sizeof(candidate));
            fd = connect_gateway(candidate);
        }
        if (fd < 0) { b1_link_failed(&link_retry,uptime_ms());continue; }
        rx_buffer_t rx = {0};
        if (!register_node(fd, candidate, &rx)) {
            close(fd);
            b1_link_failed(&link_retry,uptime_ms());
            continue;
        }
chosen=fd;break;}
assert(chosen==22);puts("A1 TCP accepted / registration rejected -> A2 registered PASS");}
