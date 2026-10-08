#include "change_detector.h"
#include "adaptive_scheduler.h"
#include <stdio.h>

int main(void) {
    cd_config_t cd={0}; as_config_t cfg={0}; float ladders[3][8];
    for (int c=0;c<4;c++) {
        int use;
        if (scanf("%d %f",&use,&cd.channels[c].noise_floor)!=2) return 1;
        cd.channels[c].use=cfg.delta_channel_use[c]=use!=0;
        cfg.delta_noise_floor[c]=cd.channels[c].noise_floor;
    }
    if (scanf("%f %f %f %f %f %f",&cd.variety_window_s,&cd.roc_window_s,&cd.baseline_tau_s,
        &cd.min_interval_s,&cd.event_threshold,&cd.event_min_duration_s)!=6) return 1;
    if (scanf("%f %f %f %f %f %f",&cfg.min_interval,&cfg.default_interval,&cfg.max_interval,
        &cfg.stable_threshold,&cfg.active_threshold,&cfg.hysteresis_fraction)!=6) return 1;
    for (int s=0;s<3;s++) {
        int len;
        if (scanf("%d %d",&len,&cfg.ladder_confirm[s])!=2 || len<1 || len>8) return 1;
        cfg.ladder_len[s]=(size_t)len; cfg.ladders[s]=ladders[s];
        for (int i=0;i<len;i++) if (scanf("%f",&ladders[s][i])!=1) return 1;
    }
    int first,event,state,interval;
    if (scanf("%d %d %d %d %f %f",&first,&event,&state,&interval,&cfg.heartbeat_s,&cfg.delta_threshold)!=6) return 1;
    cfg.up_first_sample=first;cfg.up_on_event=event;cfg.up_on_state_change=state;cfg.up_on_interval_change=interval;
    cd_t detector;as_t scheduler;cd_init(&detector,&cd);as_init(&scheduler,&cfg);
    double t;float v[4];int mask;
    while (scanf("%lf %f %f %f %f %d",&t,&v[0],&v[1],&v[2],&v[3],&mask)==6) {
        bool valid[4];for(int c=0;c<4;c++)valid[c]=(mask&(1<<c))!=0;
        bool detected;float score=cd_update(&detector,t,v,valid,&detected);
        as_decision_t out;as_update(&scheduler,t,v,valid,score,detected,&out);
        printf("%d %.9g %d %d\n",out.state,out.interval_s,out.detected_event,out.upload_requested);
    }
    return 0;
}
