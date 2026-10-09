#include "agri_lora.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned digit(char c) {
  return c <= '9' ? (unsigned)(c - '0') : (unsigned)(c - 'a' + 10);
}
int main(void) {
  static al_receiver_t receiver;
  al_receiver_init(&receiver);
  static uint8_t out[AL_MAX_MESSAGE], wire[AL_MAX_FRAME], encoded[AL_MAX_FRAME];
  char line[AL_MAX_FRAME * 2 + 8];
  uint64_t now = 0;
  while (fgets(line, sizeof(line), stdin)) {
    size_t n = strcspn(line, "\n");
    assert(n % 2 == 0 && n / 2 <= sizeof(wire));
    n /= 2;
    for (size_t i = 0; i < n; ++i)
      wire[i] = (uint8_t)(digit(line[2 * i]) * 16 + digit(line[2 * i + 1]));
    al_frame_t f;
    size_t len = 0;
    if (!al_decode(wire, n, &f)) {
      puts("REJECTED");
      continue;
    }
    assert(al_encode(&f, encoded, sizeof(encoded), &len) && len == n &&
           !memcmp(wire, encoded, n));
    al_frame_t meta;
    int rc =
        al_receive(&receiver, wire, n, ++now, out, sizeof(out), &len, &meta);
    if (rc == 1) {
      fwrite(out, 1, len, stdout);
      putchar('\n');
    } else
      puts(rc < 0 ? "REJECTED" : "PARTIAL");
    al_stream_t stream = {0};
    size_t result = 0;
    al_stream_byte(&stream, 'X', encoded, sizeof(encoded), &result);
    for (size_t i = 0; i < n; ++i) {
      /* A poll can end while the UART frame is arriving; no bytes lost. */
      assert(!al_stream_expire(&stream,100,200,800));
      int q =
          al_stream_byte(&stream, wire[i], encoded, sizeof(encoded), &result);
      if (i + 1 == n)
        assert(q == 1 && result == n && !memcmp(encoded, wire, n));
    }
    stream.used=12;
    assert(!al_stream_expire(&stream,100,899,800));
    assert(al_stream_expire(&stream,100,900,800) && stream.used==0);
    stream.used=12;
    assert(al_stream_expire(&stream,100,99,800) && stream.used==0);
  }
  return 0;
}
