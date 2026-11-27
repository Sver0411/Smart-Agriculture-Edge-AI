# Live XQUIC gateway backhaul

One bridge pair connects one gateway's existing TCP JSON-lines session to the existing cloud Server. The gateway bridge accepts TCP and the cloud bridge connects to Server over TCP. Between them a real encrypted XQUIC connection negotiates multipath version 10 across two IPv4/UDP endpoint pairs. No workload file or generated payload is used.

On the uplink the bridge calls the upstream FAP-MPQUIC fresh-aware path selector for each live message. Its inputs include the two paths' measured RTT, congestion window, loss, outstanding bytes and freshness. The upstream packet scheduler binds each stream to the selected path and permits cross-path retransmission. Downlink uses native minimum-RTT scheduling. One QUIC stream carries one original JSON line. The receiver restores order before forwarding to TCP. Outstanding streams, buffered records and frame lengths are bounded. Backpressure propagates back to TCP. If these bounds are exceeded the session closes and the gateway's normal replay logic applies.

The bridge preserves application semantics. It never synthesizes a durable receipt and never discards an old sample in favor of a new one. Clouds persist and deduplicate history, issue PERSISTED_ACK on commit and push policy on the reverse connection. The gateway retains messages until it verifies those receipts. Path-selection budgets default to 1,000 ms for events/commands/results/receipts/policy and 5,000 ms for ordinary telemetry and status. They describe urgency at this gateway-to-cloud hop. Exceeding a budget does not expire a durable business message. The upstream overwriteable workload queue is not used here.

## Build on Linux

The build needs Git, CMake 3.24+, Ninja, a C/C++ toolchain and the pinned scheduler's BoringSSL build dependencies. Fetch the scheduler at the commit below and initialize its XQUIC submodule. The upstream script prepares the exact XQUIC patches, fetches BoringSSL and builds its static libraries. The bridge reuses that configured build.

```bash
git clone --filter=blob:none --no-checkout https://github.com/Sver0411/IoT-MPQUIC-Scheduler.git /tmp/agri-scheduler
git -C /tmp/agri-scheduler sparse-checkout init --cone
git -C /tmp/agri-scheduler sparse-checkout set src scripts patches tests configs third_party/xquic
git -C /tmp/agri-scheduler checkout --detach 1b3bea9f8933cf70713610fa550aa4ab670d71e4
git -C /tmp/agri-scheduler submodule update --init --depth 1 third_party/xquic
bash backhaul/build.sh /tmp/agri-scheduler /tmp/agri-build
```

## Start a laboratory lane

Use a fresh self-signed leaf certificate for the named research peer. The gateway verifies the pinned certificate and hostname. The cloud endpoint uses configured UDP peer addresses. This lab bridge does not implement gateway certificate authentication or enable the farm's deployment profile.

```bash
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=agri-backhaul \
  -addext subjectAltName=DNS:agri-backhaul -keyout /tmp/agri.key -out /tmp/agri.crt
python3 -m backhaul.bridge cloud --tcp 127.0.0.1:9100 --local 127.0.0.21:4443 127.0.0.22:4443 \
  --peer 127.0.0.11:4444 127.0.0.12:4444 --cert /tmp/agri.crt --key /tmp/agri.key \
  --binary /tmp/agri-build/bridge/agri-mpquic
# In a separate terminal
python3 -m backhaul.bridge gateway --tcp 127.0.0.1:19101 --local 127.0.0.11:4444 127.0.0.12:4444 \
  --peer 127.0.0.21:4443 127.0.0.22:4443 --cert /tmp/agri.crt --binary /tmp/agri-build/bridge/agri-mpquic
```

Start Server on port 9100 and point A1's server host/port to 127.0.0.1:19101. For A2 use a second gateway TCP listener and a second set of UDP ports for both bridge processes. The cloud TCP backend may be shared. Loopback needs no network namespaces or elevated privileges. Separate routed interfaces or Linux network emulation can be substituted by changing the four UDP addresses.

The supervisors reopen sessions after disconnect. An idle Linux poll waits for IPC, UDP or an XQUIC timer. The gateway uses finite reconnection backoff and preserves its normal SQLite outbox. Each bridge's stderr includes JSON events `paths_validated`, `path_selected`, `frame` and `udp_summary`, alongside native errors if present. `frame` includes direction, original message ID, type and length. `--trace` additionally writes upstream packet-level diagnostics, including the actual selected path and retransmissions, to stdout.

## Source provenance

| Component | Version and source | Reuse |
| --- | --- | --- |
| IoT-MPQUIC-Scheduler | [1b3bea9](https://github.com/Sver0411/IoT-MPQUIC-Scheduler/tree/1b3bea9f8933cf70713610fa550aa4ab670d71e4), MIT | Endpoint UDP/path callbacks, FAP-MPQUIC initial-path selection, XQUIC stream affinity and cross-path repair. The live build reuses the bounded binding table across successive stream IDs with identity checks. |
| Alibaba XQUIC | [dffd32c](https://github.com/alibaba/xquic/tree/dffd32c42a511edae544b87169976516b7c4cbfa), Apache-2.0 | XQUIC connection, TLS integration, congestion control, datagram and stream processing. The scheduler's three research patches are applied by its build script. |
| BoringSSL | [b69a617](https://github.com/google/boringssl/tree/b69a6175320af9b6fca7295fdbb4fb130f4804a2) | TLS. See the upstream LICENSE for attribution and individual file terms. |

### Seven-role validation

After building the native endpoint on Linux, from the repository root run:

```sh
python3 scripts/run_research_backhaul.py --binary "$build/bridge/agri-mpquic" --output /tmp/agri-live-run
```

Choose a new output directory. The launcher creates an ephemeral server certificate, starts the A1 and A2 bridges, and verifies the triggering B1 sample, C1 command and execution result crossed A1's encrypted connection. It checks both gateways for cloud commit receipts and reverse policy traffic. `summary.json`, `backhaul.json`, the application databases and per-lane logs contain the evidence. The [Linux CI job](../.github/workflows/research-chain.yml) also runs the three preceding configurations, then injects 35 ms latency on the primary route inside a disposable network namespace. All four configurations use synthetic sensor inputs and simulated actuators. The LoRa segment runs on a host field-channel model.
