/* Reuse pinned IoT-MPQUIC-Scheduler's Linux/XQUIC engine callbacks, UDP path
 * mapping and instrumentation. Its benchmark main/workload is never invoked. */
#define main iot_benchmark_main
#include "transport/endpoint.c"
#undef main

#include <limits.h>
#include <openssl/crypto.h>

enum { LINE_MAX_BYTES = 65537, META_BYTES = 5, REORDER_WINDOW = 128 };
static const char *bridge_alpn = "agri-backhaul-v1";
struct live_stream {
    size_t used, size;
    bool tx, writing, finished;
    unsigned char line[LINE_MAX_BYTES + 1];
};
struct complete_line {
    size_t size;
    unsigned char data[];
};
struct bridge_session {
    int ipc;
    unsigned char pin[SHA256_DIGEST_LENGTH];
    bool pinned, local_eof;
    uint64_t next_tx, next_rx, retry_at, handshake_at, pending_at;
    size_t pending;
    unsigned char packet[META_BYTES + LINE_MAX_BYTES];
    struct complete_line *received[REORDER_WINDOW];
};
static struct bridge_session live;

static const char *role(const struct endpoint *ep)
{
    return ep->server ? "cloud" : "gateway";
}

static int verify_pin(const unsigned char *certs[], const size_t sizes[], size_t count, void *user)
{
    (void)user;
    unsigned char digest[SHA256_DIGEST_LENGTH];
    live.pinned = count && SHA256(certs[0], sizes[0], digest) &&
                  CRYPTO_memcmp(live.pin, digest, sizeof(digest)) == 0;
    return live.pinned ? 0 : -1;
}

static void on_handshake(xqc_connection_t *conn, void *user, void *proto)
{
    struct endpoint *ep = user;
    if (!ep->server && !live.pinned) {
        ep->failed = true;
        return;
    }
    live.handshake_at = now_us();
    handshake_finished(conn, user, proto);
}

static int read_address(const char *arg, struct sockaddr_in *addr)
{
    const char *colon = strrchr(arg, ':');
    char ip[INET_ADDRSTRLEN], *end;
    if (!colon || colon == arg || (size_t)(colon - arg) >= sizeof(ip))
        return -1;
    memcpy(ip, arg, colon - arg);
    ip[colon - arg] = 0;
    long port = strtol(colon + 1, &end, 10);
    if (*end || port < 1 || port > 65535 || inet_pton(AF_INET, ip, &addr->sin_addr) != 1)
        return -1;
    addr->sin_family = AF_INET;
    addr->sin_port = htons((uint16_t)port);
    return 0;
}

static xqc_int_t open_stream(xqc_stream_t *stream, void *user)
{
    if (user)
        return 0;
    if (xqc_stream_get_direction(stream) != XQC_STREAM_UNI)
        return -1;
    struct live_stream *frame = calloc(1, sizeof(*frame));
    if (!frame)
        return -1;
    xqc_stream_set_user_data(stream, frame);
    return 0;
}

static xqc_int_t send_stream(xqc_stream_t *stream, void *user)
{
    struct live_stream *frame = user;
    if (!frame || !frame->tx || frame->finished || frame->writing)
        return 0;
    frame->writing = true;
    size_t offered = frame->size - frame->used;
    ssize_t n = xqc_stream_send(stream, frame->line + frame->used, offered, 1);
    frame->writing = false;
    if (n == -XQC_EAGAIN)
        return 0;
    if (n < 0 || (size_t)n > offered)
        return -1;
    frame->used += (size_t)n;
    frame->finished = frame->used == frame->size;
    return 0;
}

static xqc_int_t recv_stream(xqc_stream_t *stream, void *user)
{
    struct live_stream *frame = user;
    struct endpoint *ep = xqc_get_conn_user_data_by_stream(stream);
    if (!frame || frame->tx)
        return -1;
    while (!frame->finished) {
        uint8_t fin = 0;
        ssize_t n = xqc_stream_recv(stream, frame->line + frame->used,
                                    sizeof(frame->line) - frame->used, &fin);
        if (n == -XQC_EAGAIN)
            return 0;
        if (n < 0 || (frame->used += (size_t)n) > LINE_MAX_BYTES)
            break;
        if (fin) {
            uint64_t ordinal = xqc_stream_id(stream) / 4;
            size_t slot = ordinal % REORDER_WINDOW;
            if (ordinal < live.next_rx || ordinal - live.next_rx >= REORDER_WINDOW ||
                live.received[slot] || !frame->used || frame->line[frame->used - 1] != '\n')
                break;
            /* The stream owns its buffer through close. The ordered IPC queue
             * owns a separate copy and can drain after the XQUIC callback. */
            struct complete_line *completed = malloc(sizeof(*completed) + frame->used);
            if (!completed)
                break;
            memcpy(completed->data, frame->line, frame->used);
            completed->size = frame->used;
            live.received[slot] = completed;
            frame->finished = true;
        } else if (!n) {
            return 0;
        }
    }
    if (frame->finished)
        return 0;
    ep->failed = true;
    return -1;
}

static xqc_int_t close_stream(xqc_stream_t *stream, void *user)
{
    struct live_stream *frame = user;
    if (!frame)
        return 0;
    struct endpoint *ep = xqc_get_conn_user_data_by_stream(stream);
    if (!frame->finished)
        ep->failed = true;
    if (frame->tx) {
        ep->active_tx--;
        if (!ep->server)
            ep->iot->paths.bindings[(xqc_stream_id(stream) / 4) % IOT_MAX_RECORDS].id = 0;
    }
    free(frame);
    return 0;
}

static void maintain_paths(struct endpoint *ep)
{
    if (!ep->conn || !ep->handshake || ep->quic_closing)
        return;
    if (!ep->server && ep->create_path && ep->links[1].id == UINT64_MAX) {
        uint64_t id;
        ep->create_path = false;
        int rc = xqc_conn_create_path(ep->engine, &ep->cid, &id, 0);
        if (!rc)
            map_link(&ep->links[1], 1, id);
        else if (rc != -XQC_EMP_NO_AVAIL_PATH_ID)
            ep->failed = true;
    }
    if (!ep->validated && xqc_conn_available_paths(ep->engine, &ep->cid) == PATHS) {
        ep->validated = true;
        fprintf(stderr, "{\"event\":\"paths_validated\",\"role\":\"%s\",\"count\":2}\n", role(ep));
    }
}

static void forward_to_quic(struct endpoint *ep)
{
    uint64_t now = now_us();
    if (!live.pending || !ep->conn || !ep->handshake || ep->quic_closing ||
        (!ep->validated && now < live.handshake_at + 1000000) || now < live.retry_at ||
        ep->active_tx >= IOT_WINDOW)
        return;
    uint64_t ordinal = live.next_tx;
    struct iot_binding *slot = &ep->iot->paths.bindings[ordinal % IOT_MAX_RECORDS];
    if (!ep->server && slot->id)
        return;
    if (ordinal >= UINT32_MAX) {
        live.local_eof = true;
        return;
    }
    struct iot_path_sample paths[PATHS] = {0};
    size_t count = ep->server ? 0 : iot_path_samples(ep->conn, paths, PATHS, 1.0, true);
    if (!ep->server && !count)
        return;
    for (size_t i = 0; i < count; i++)
        for (int j = 0; j < PATHS; j++)
            if (ep->links[j].id == paths[i].id)
                paths[i].last_probe_us = ep->links[j].last_probe_us;
    size_t length = live.pending - META_BYTES;
    uint32_t budget_us = iot_read_u32(live.packet + 1);
    struct iot_record record = {.id = (uint32_t)(ordinal + 1), .kind = live.packet[0],
                                .payload_len = (uint32_t)length};
    uint64_t due = live.pending_at + budget_us;
    double slack = (double)due - now;
    size_t chosen = ep->server ? 0 : iot_choose_initial_path(&record, slack, paths, count, IOT_FRESH_AWARE, 0);
    struct live_stream *frame = calloc(1, sizeof(*frame));
    if (!frame) {
        ep->failed = true;
        return;
    }
    frame->tx = true;
    frame->size = length;
    memcpy(frame->line, live.packet + META_BYTES, length);
    xqc_stream_t *stream = xqc_stream_create_with_direction(ep->conn, XQC_STREAM_UNI, frame);
    if (!stream) {
        free(frame);
        live.retry_at = now + 25000;
        return;
    }
    uint64_t id = xqc_stream_id(stream);
    if (id / 4 != ordinal) {
        ep->failed = true;
        return;
    }
    if (!ep->server) {
        *slot = (struct iot_binding){.id = record.id, .due_us = due,
                                     .home = paths[chosen].id};
        for (int i = 0; i < PATHS; i++)
            if (ep->links[i].id == paths[chosen].id)
                ep->links[i].last_probe_us = paths[chosen].sampled_us;
        fprintf(stderr, "{\"event\":\"path_selected\",\"role\":\"gateway\","
                "\"algorithm\":\"FAP-MPQUIC\",\"stream_id\":%" PRIu64 ",\"path_id\":%" PRIu64
                ",\"bytes\":%zu,\"candidates\":%zu}\n", id, paths[chosen].id, length, count);
    }
    ep->active_tx++;
    live.next_tx++;
    live.pending = 0;
    if (send_stream(stream, frame) != 0)
        ep->failed = true;
}

static void handle_ipc(struct endpoint *ep, short revents)
{
    if (revents & POLLOUT) {
        size_t slot = live.next_rx % REORDER_WINDOW;
        struct complete_line *frame = live.received[slot];
        if (frame) {
            ssize_t n = send(live.ipc, frame->data, frame->size, MSG_DONTWAIT | MSG_NOSIGNAL);
            if (n == (ssize_t)frame->size) {
                free(frame);
                live.received[slot] = NULL;
                live.next_rx++;
            } else if (n >= 0 || (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR)) {
                ep->failed = true;
            }
        }
    }
    if (revents & POLLIN) {
        ssize_t n = recv(live.ipc, live.packet, sizeof(live.packet), MSG_DONTWAIT | MSG_TRUNC);
        if (!n)
            live.local_eof = true;
        else if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR))
            return;
        else if (n <= META_BYTES || n > (ssize_t)sizeof(live.packet) ||
                 (live.packet[0] != IOT_EVENT && live.packet[0] != IOT_STATE) ||
                 !iot_read_u32(live.packet + 1) || live.packet[n - 1] != '\n')
            ep->failed = true;
        else {
            live.pending = (size_t)n;
            live.pending_at = now_us();
        }
    }
    if (revents & (POLLHUP | POLLERR | POLLNVAL))
        live.local_eof = true;
}

static void run_bridge(struct endpoint *ep)
{
    while (!ep->closed && !ep->failed && !live.local_eof) {
        uint64_t now = now_us();
        if (now >= ep->timer) {
            ep->timer = UINT64_MAX;
            xqc_engine_main_logic(ep->engine);
        }
        maintain_paths(ep);
        forward_to_quic(ep);
        if (ep->closed || ep->failed || live.local_eof)
            break;
        struct pollfd fds[PATHS + 1];
        for (int i = 0; i < PATHS; i++)
            fds[i] = (struct pollfd){.fd = ep->links[i].fd,
                         .events = POLLIN | (ep->links[i].blocked ? POLLOUT : 0)};
        fds[PATHS] = (struct pollfd){.fd = live.ipc, .events = (live.pending ? 0 : POLLIN) |
                                 (live.received[live.next_rx % REORDER_WINDOW] ? POLLOUT : 0)};
        now = now_us();
        uint64_t wake = ep->timer;
        if (live.pending && live.retry_at > now && live.retry_at < wake)
            wake = live.retry_at;
        uint64_t startup = live.handshake_at + 1000000;
        if (ep->handshake && !ep->validated && live.pending && startup > now && startup < wake)
            wake = startup;
        int ms = wake == UINT64_MAX ? -1 : wake <= now ? 0 :
                 (int)fmin(INT_MAX, ceil((double)(wake - now) / 1000));
        if (poll(fds, PATHS + 1, ms) < 0) {
            if (errno != EINTR)
                ep->failed = true;
            continue;
        }
        for (int i = 0; i < PATHS; i++) {
            if (fds[i].revents & (POLLIN | POLLERR))
                receive_packets(ep, i);
            if (fds[i].revents & POLLOUT) {
                ep->links[i].blocked = false;
                if (ep->conn)
                    xqc_conn_continue_send_by_conn(ep->conn);
            }
        }
        handle_ipc(ep, fds[PATHS].revents);
    }
    if (ep->conn && !ep->quic_closing) {
        xqc_conn_close(ep->engine, &ep->cid);
        xqc_engine_main_logic(ep->engine);
    }
}

int main(int argc, char **argv)
{
    /* bridge.py owns CLI validation, localhost TCP, child lifetime and ordered IPC. */
    bool server = argc > 1 && !strcmp(argv[1], "cloud");
    if ((server && argc != 9) || (!server && (argc != 8 || strcmp(argv[1], "gateway"))))
        return 2;
    char *end;
    live.ipc = (int)strtol(argv[2], &end, 10);
    if (*end || live.ipc < 0)
        return 2;
    if (!server) {
        if (strlen(argv[7]) != SHA256_DIGEST_LENGTH * 2)
            return 2;
        for (size_t i = 0; i < sizeof(live.pin); i++)
            if (sscanf(argv[7] + 2 * i, "%2hhx", &live.pin[i]) != 1)
                return 2;
    }
    struct endpoint ep = {.server = server, .timer = UINT64_MAX, .trace = stderr};
    for (int i = 0; i < PATHS; i++)
        ep.links[i].fd = -1;
    ep.iot = calloc(1, sizeof(*ep.iot));
    if (!ep.iot)
        return 1;
    ep.iot->bind_path = !server;
    ep.iot->paths.cross = !server;
    for (int i = 0; i < PATHS; i++) {
        struct link *link = &ep.links[i];
        link->id = UINT64_MAX;
        if (read_address(argv[3 + i], &link->local) || read_address(argv[5 + i], &link->peer))
            goto fail;
        link->fd = open_link_socket(&link->local, &link->peer);
        if (link->fd < 0) {
            perror("binding MPQUIC UDP path");
            goto fail;
        }
    }
    map_link(&ep.links[0], 0, 0);
    xqc_engine_type_t type = server ? XQC_ENGINE_SERVER : XQC_ENGINE_CLIENT;
    xqc_config_t config;
    if (xqc_engine_get_default_config(&config, type) != 0)
        goto fail;
    config.cfg_log_level = XQC_LOG_ERROR;
    xqc_engine_ssl_config_t tls = {0};
    if (server) {
        tls.cert_file = argv[7];
        tls.private_key_file = argv[8];
    }
    xqc_engine_callback_t callbacks = {
        .set_event_timer = set_timer, .monotonic_ts = now_us,
        .log_callbacks = {.xqc_log_write_err = trace_log},
    };
    xqc_transport_callbacks_t transport = {
        .server_accept = server ? accept_connection : NULL,
        .write_socket = write_initial, .write_socket_ex = write_path,
        .save_token = discard_token, .save_session_cb = discard_ticket,
        .conn_update_cid_notify = cid_updated, .conn_closing = conn_closing,
        .ready_to_create_path_notify = path_ready,
        .path_created_notify = server ? path_created : NULL,
        .path_removed_notify = path_removed, .cert_verify_cb = server ? NULL : verify_pin,
    };
    xqc_app_proto_callbacks_t app = {
        .conn_cbs = {.conn_create_notify = conn_open, .conn_close_notify = conn_closed,
                     .conn_handshake_finished = on_handshake},
        .stream_cbs = {.stream_create_notify = open_stream, .stream_read_notify = recv_stream,
                       .stream_write_notify = send_stream, .stream_close_notify = close_stream},
    };
    xqc_conn_settings_t settings = {
        .proto_version = XQC_VERSION_V1, .enable_multipath = 1, .multipath_version = XQC_MULTIPATH_10,
        .init_max_path_id = 1, .max_streams_uni = IOT_WINDOW, .sndq_packets_used_max = IOT_SEND_PACKETS,
        .scheduler_callback = server ? xqc_minrtt_scheduler_cb : iot_affinity_callback,
        .cong_ctrl_callback = xqc_cubic_cb, .pacing_on = 1,
        .init_idle_time_out = 10000, .idle_time_out = 30000, .ping_on = 1,
    };
    ep.engine = xqc_engine_create(type, &config, &tls, &callbacks, &transport, &ep);
    if (!ep.engine || xqc_engine_register_alpn(ep.engine, bridge_alpn, strlen(bridge_alpn), &app, NULL))
        goto fail;
    if (server) {
        xqc_server_set_conn_settings(ep.engine, &settings);
    } else {
        xqc_conn_ssl_config_t verify = {
            .cert_verify_flag = XQC_TLS_CERT_FLAG_NEED_VERIFY | XQC_TLS_CERT_FLAG_ALLOW_SELF_SIGNED,
        };
        const xqc_cid_t *cid = xqc_connect(ep.engine, &settings, NULL, 0, "agri-backhaul", 0, &verify,
                                           (struct sockaddr *)&ep.links[0].peer, sizeof(ep.links[0].peer),
                                           bridge_alpn, &ep);
        if (!cid)
            goto fail;
        ep.cid = *cid;
    }
    run_bridge(&ep);
    goto cleanup;
fail:
    ep.failed = true;
cleanup:
    if (ep.engine)
        xqc_engine_destroy(ep.engine);
    for (int i = 0; i < PATHS; i++) {
        struct link *link = &ep.links[i];
        fprintf(stderr, "{\"event\":\"udp_summary\",\"role\":\"%s\",\"link\":%d,"
                "\"tx_packets\":%" PRIu64 ",\"rx_packets\":%" PRIu64 "}\n",
                role(&ep), i, link->tx, link->rx);
        if (link->fd >= 0)
            close(link->fd);
    }
    for (size_t i = 0; i < REORDER_WINDOW; i++)
        free(live.received[i]);
    free(ep.iot);
    return ep.failed ? 1 : 0;
}
