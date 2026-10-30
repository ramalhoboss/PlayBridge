# Stream health and diagnostic export

The status bar displays the dimensions of the last decoded video frame. These are source-stream dimensions, independent of window size. The received Mbps value measures media payload arriving at the PC over a rolling five-second window; it becomes available after at least one second. It is not the encoder's configured target or total network bandwidth.

Open Settings and choose **Export diagnostics** to save a ZIP containing diagnostics.json and a short explanation. It includes measured resolution, received bitrate, audio queue/underrun counters and PC-stage timing percentiles. IP addresses, output-device names, file paths, exception logs, screenshots, audio and arbitrary acknowledgement fields are excluded. Review any diagnostic file before sharing.

Timings describe PC processing. They do not measure total console-to-screen latency. Video packet rate is separate from decoded/presented frame rate. Metrics reset their stream window when a new session starts.

PlayBridge does not implement virtual microphone, controller feedback, live bitrate adjustment or HDR. The 1440p and 4K profiles are described in [capture options](CAPTURE-OPTIONS.md).

## Console discovery

Open Settings > Find console. PlayBridge listens for PS5 LAN discovery replies and scans a bounded local /24 on up to two IPv4 interfaces for a matching PS5 Payload Manager web service. Choose a discovered console or enter an IPv4 address manually. Save changes reconnects using the selected address. Discovery does not wake the console or start Payload Manager. VPNs, network isolation and firewall rules can prevent discovery; manual IP remains available.
