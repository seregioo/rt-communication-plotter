# RT Communication Plotter

CLI tool for analyzing CSV traces from a real-time communication loop.

## Features

- Latency analysis across operation, write, read, and end-to-end stages
- Consistency analysis between transmitted and received values
- Real-time deviation analysis against a configurable target cycle time
- Explicit deadline-miss and negative-slack tracking
- Saved plots plus a compact terminal summary

## Usage

```bash
uv run rt-communication-plotter trace.csv
```

```bash
uv run rt-communication-plotter trace.csv --target-cycle-us 100 --output-dir plots --show-plots
```

```bash
uv run rt-communication-plotter trace.csv --input-time-unit ns
```

## Expected CSV columns

```text
x_trans,x_recv,time_at_begin_ns,time_after_op_ns,time_after_send_ns,time_after_receive_ns
```

The plotter reports timing metrics in microseconds. Use `--input-time-unit ns` for raw
nanosecond timestamps and `--input-time-unit us` if the CSV already stores those raw
timestamp columns in microseconds.

## Metric Definitions

- `cycle_duration_us`: time between consecutive loop starts, computed from `time_at_begin_ns`
- `jitter_us`: `cycle_duration_us - target_cycle_us`
- `op_duration_us`: `time_after_op_ns - time_at_begin_ns`
- `write_latency_us`: `time_after_send_ns - time_after_op_ns`
- `read_latency_us`: `time_after_receive_ns - time_after_send_ns`
- `end_to_end_latency_us`: `time_after_receive_ns - time_at_begin_ns`
- `sleep_after_receive_us`: time remaining between the end of the current read and the next loop start
- `deadline_miss`: `end_to_end_latency_us > target_cycle_us`
- `negative_slack`: `sleep_after_receive_us <= 0`
- `rolling mean`: moving average over the last `N` samples, where `N` is `--rolling-window`

## How To Read The Plots

- Use `cycle_duration_us` and `jitter_us` to judge periodicity.
- Use `end_to_end_latency_us` to judge whether one full iteration fits inside the budget.
- Use `sleep_after_receive_us` to judge how much slack remains after the DAQ read.
- Use `deadline_miss` and `negative_slack` counts in the terminal summary to see direct constraint violations.
