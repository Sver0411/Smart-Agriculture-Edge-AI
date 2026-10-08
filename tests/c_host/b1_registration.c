#include "b1_registration.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static cJSON *reply(const char *source,const char *owner,unsigned generation,bool accepted) {
 cJSON *m=cJSON_CreateObject(),*p=cJSON_CreateObject();
 cJSON_AddStringToObject(m,"type","NODE_REGISTER_ACK");cJSON_AddStringToObject(m,"source",source);
 cJSON_AddStringToObject(m,"target","B1");cJSON_AddItemToObject(m,"payload",p);
 cJSON_AddStringToObject(p,"owner_gateway",owner);cJSON_AddNumberToObject(p,"generation",generation);
 cJSON_AddBoolToObject(p,"accepted",accepted);cJSON_AddStringToObject(p,"reason","NOT_OWNER");return m;
}
int main(void) {
 b1_registration_t s={.generation=1,.owner="A1"};cJSON *m=reply("A1","A1",1,true);
 assert(b1_registration_reply(&s,m,"A1")==B1_REG_ACCEPTED);cJSON_Delete(m);
 m=reply("A1","A2",2,false);assert(b1_registration_reply(&s,m,"A1")==B1_REG_NOT_OWNER);cJSON_Delete(m);
 assert(s.generation==2 && !strcmp(s.owner,"A2"));
 m=reply("A2","A2",2,true);assert(b1_registration_reply(&s,m,"A2")==B1_REG_ACCEPTED);cJSON_Delete(m);
 m=reply("A1","A1",1,true);assert(b1_registration_reply(&s,m,"A1")==B1_REG_STALE_GENERATION);cJSON_Delete(m);
 m=reply("A1","A1",2,true);assert(b1_registration_reply(&s,m,"A1")==B1_REG_STALE_GENERATION);cJSON_Delete(m);
 m=reply("A2","A1",3,true);assert(b1_registration_reply(&s,m,"A2")==B1_REG_INVALID_REPLY);cJSON_Delete(m);
 m=reply("A1","A1",3,true);assert(b1_registration_reply(&s,m,"A2")==B1_REG_INVALID_REPLY);cJSON_Delete(m);
 m=reply("A2","A2",3,true);cJSON_ReplaceItemInObject(cJSON_GetObjectItem(m,"payload"),"generation",cJSON_CreateNumber(1.5));
 assert(b1_registration_reply(&s,m,"A2")==B1_REG_INVALID_REPLY);cJSON_Delete(m);
 assert(s.generation==2 && !strcmp(s.owner,"A2"));puts("registration: redirect, standby, epoch rollback, malformed PASS");
}
