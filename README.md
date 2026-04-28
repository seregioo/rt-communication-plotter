# RT Communication Plotter

CLI tool for analyzing CSV traces from a real-time communication loop.

## Features

- Latency analysis across operation, write, read, and end-to-end stages
- Consistency analysis between transmitted and received values
- Real-time deviation analysis against a configurable target cycle time
- Saved plots plus a compact terminal summary

## Usage

```bash
uv run rt-communication-plotter trace.csv
```

```bash
uv run rt-communication-plotter trace.csv --target-cycle-us 100 --output-dir plots --show-plots
```

## Expected CSV columns

```text
x_trans,x_recv,time_at_begin_ns,time_after_op_ns,time_after_send_ns,time_after_receive_ns
```
