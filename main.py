from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import matplotlib.pyplot as plt
import pandas as pd

NANOSECONDS_PER_MICROSECOND: Final[float] = 1_000.0


@dataclass(frozen=True)
class AnalysisConfig:
    """Runtime configuration for the CSV plotter."""

    input_csv: Path
    output_dir: Path
    input_time_unit: str
    target_cycle_us: float
    rolling_window: int
    show_plots: bool


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line argument parser."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description=(
            "Analyze a real-time communication CSV trace and generate latency, "
            "consistency, and real-time deviation plots."
        )
    )
    parser.add_argument(
        "input_csv",
        type=Path,
        help="Path to the CSV trace to analyze.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("plots"),
        help="Directory where generated plots will be written. Default: %(default)s",
    )
    parser.add_argument(
        "--input-time-unit",
        choices=("ns", "us"),
        default="ns",
        help=(
            "Unit used by the raw timestamp columns in the CSV. "
            "Default: %(default)s"
        ),
    )
    parser.add_argument(
        "--target-cycle-us",
        type=float,
        default=100.0,
        help=(
            "Expected real-time cycle period in microseconds. "
            "Used to measure deviation from real time. Default: %(default)s"
        ),
    )
    parser.add_argument(
        "--rolling-window",
        type=int,
        default=25,
        help="Window size for smoothing trend lines. Default: %(default)s",
    )
    parser.add_argument(
        "--show-plots",
        action="store_true",
        help="Display plots interactively in addition to saving them to disk.",
    )
    return parser


def parse_args() -> AnalysisConfig:
    """Parse CLI arguments into a typed configuration object."""
    parser: argparse.ArgumentParser = build_parser()
    arguments: argparse.Namespace = parser.parse_args()

    if arguments.target_cycle_us <= 0:
        parser.error("--target-cycle-us must be greater than zero.")
    if arguments.rolling_window <= 0:
        parser.error("--rolling-window must be greater than zero.")

    return AnalysisConfig(
        input_csv=arguments.input_csv,
        output_dir=arguments.output_dir,
        input_time_unit=arguments.input_time_unit,
        target_cycle_us=arguments.target_cycle_us,
        rolling_window=arguments.rolling_window,
        show_plots=arguments.show_plots,
    )


def load_trace(input_csv: Path) -> pd.DataFrame:
    """Load and validate the required trace columns."""
    required_columns: set[str] = {
        "x_trans",
        "x_recv",
        "time_at_begin_ns",
        "time_after_op_ns",
        "time_after_send_ns",
        "time_after_receive_ns",
    }
    trace: pd.DataFrame = pd.read_csv(input_csv)
    missing_columns: list[str] = sorted(required_columns.difference(trace.columns))
    if missing_columns:
        missing_text: str = ", ".join(missing_columns)
        raise ValueError(f"Input CSV is missing required columns: {missing_text}")

    return trace


def to_us(series: pd.Series, input_time_unit: str) -> pd.Series:
    """Convert raw timestamp data to microseconds."""
    converted: pd.Series = series.astype("float64")
    if input_time_unit == "ns":
        return converted / NANOSECONDS_PER_MICROSECOND
    return converted


def compute_metrics(
    trace: pd.DataFrame, target_cycle_us: float, input_time_unit: str
) -> pd.DataFrame:
    """Derive analysis metrics from the raw trace."""
    metrics: pd.DataFrame = trace.copy()

    metrics["op_duration_us"] = to_us(
        metrics["time_after_op_ns"] - metrics["time_at_begin_ns"], input_time_unit
    )
    metrics["write_latency_us"] = to_us(
        metrics["time_after_send_ns"] - metrics["time_after_op_ns"], input_time_unit
    )
    metrics["read_latency_us"] = to_us(
        metrics["time_after_receive_ns"] - metrics["time_after_send_ns"],
        input_time_unit,
    )
    metrics["end_to_end_latency_us"] = to_us(
        metrics["time_after_receive_ns"] - metrics["time_at_begin_ns"],
        input_time_unit,
    )
    metrics["cycle_duration_us"] = to_us(
        metrics["time_at_begin_ns"].diff(), input_time_unit
    )
    metrics["sleep_after_receive_us"] = to_us(
        metrics["time_at_begin_ns"].shift(-1) - metrics["time_after_receive_ns"],
        input_time_unit,
    )
    metrics["jitter_us"] = metrics["cycle_duration_us"] - target_cycle_us
    metrics["deadline_miss"] = metrics["end_to_end_latency_us"] > target_cycle_us
    metrics["negative_slack"] = metrics["sleep_after_receive_us"] <= 0.0
    metrics["transmission_gap"] = metrics["x_recv"] - metrics["x_trans"]
    metrics["absolute_gap"] = metrics["transmission_gap"].abs()
    metrics["relative_gap_percent"] = (
        metrics["absolute_gap"] / metrics["x_trans"].abs().clip(lower=1e-12) * 100.0
    )

    return metrics


def save_figure(figure: plt.Figure, output_path: Path, show_plots: bool) -> None:
    """Persist a figure and optionally display it."""
    figure.tight_layout()
    figure.savefig(output_path, dpi=200, bbox_inches="tight")
    if show_plots:
        figure.show()
    plt.close(figure)


def plot_latency(metrics: pd.DataFrame, config: AnalysisConfig) -> None:
    """Plot the system latency across the communication pipeline."""
    figure, axes = plt.subplots(2, 2, figsize=(16, 10))
    figure.suptitle("Latency Analysis", fontsize=16)

    latency_columns: list[str] = [
        "op_duration_us",
        "write_latency_us",
        "read_latency_us",
        "end_to_end_latency_us",
    ]
    metrics[latency_columns].plot(ax=axes[0, 0], alpha=0.85)
    axes[0, 0].axhline(
        config.target_cycle_us,
        color="black",
        linestyle="--",
        linewidth=1.2,
        label="100 us deadline" if config.target_cycle_us == 100.0 else "Cycle deadline",
    )
    axes[0, 0].set_title("Latency Timeline")
    axes[0, 0].set_xlabel("Sample")
    axes[0, 0].set_ylabel("Latency (us)")
    axes[0, 0].legend()

    metrics[latency_columns].plot(kind="box", ax=axes[0, 1])
    axes[0, 1].set_title("Latency Distribution")
    axes[0, 1].set_ylabel("Latency (us)")

    metrics["sleep_after_receive_us"].dropna().plot(
        ax=axes[1, 0],
        color="tab:blue",
        alpha=0.7,
    )
    metrics["sleep_after_receive_us"].rolling(config.rolling_window).mean().plot(
        ax=axes[1, 0],
        color="tab:red",
        linewidth=2.0,
        label=f"Rolling mean ({config.rolling_window})",
    )
    axes[1, 0].set_title("Sleep After Receive")
    axes[1, 0].set_xlabel("Sample")
    axes[1, 0].set_ylabel("Sleep / Idle Time (us)")
    axes[1, 0].legend()

    axes[1, 1].hist(
        metrics["end_to_end_latency_us"].dropna(),
        bins=min(50, max(10, len(metrics) // 5)),
        color="tab:green",
        alpha=0.8,
    )
    axes[1, 1].axvline(
        config.target_cycle_us,
        color="black",
        linestyle="--",
        linewidth=1.2,
        label="100 us deadline" if config.target_cycle_us == 100.0 else "Cycle deadline",
    )
    axes[1, 1].set_title("End-to-End Latency Histogram")
    axes[1, 1].set_xlabel("Latency (us)")
    axes[1, 1].set_ylabel("Count")
    axes[1, 1].legend()

    save_figure(figure, config.output_dir / "latency_analysis.png", config.show_plots)


def plot_consistency(metrics: pd.DataFrame, config: AnalysisConfig) -> None:
    """Plot how closely received values follow transmitted values."""
    figure, axes = plt.subplots(2, 2, figsize=(16, 10))
    figure.suptitle("Consistency Analysis", fontsize=16)

    axes[0, 0].plot(metrics.index, metrics["x_trans"], label="Transmitted", linewidth=1.5)
    axes[0, 0].plot(metrics.index, metrics["x_recv"], label="Received", linewidth=1.5, alpha=0.8)
    axes[0, 0].set_title("Transmitted vs Received Signal")
    axes[0, 0].set_xlabel("Sample")
    axes[0, 0].set_ylabel("Value")
    axes[0, 0].legend()

    axes[0, 1].scatter(metrics["x_trans"], metrics["x_recv"], alpha=0.6, s=20)
    min_value: float = float(min(metrics["x_trans"].min(), metrics["x_recv"].min()))
    max_value: float = float(max(metrics["x_trans"].max(), metrics["x_recv"].max()))
    axes[0, 1].plot([min_value, max_value], [min_value, max_value], "r--", linewidth=1.2)
    axes[0, 1].set_title("Parity Plot")
    axes[0, 1].set_xlabel("Transmitted Value")
    axes[0, 1].set_ylabel("Received Value")

    metrics["transmission_gap"].plot(ax=axes[1, 0], color="tab:orange")
    metrics["transmission_gap"].rolling(config.rolling_window).mean().plot(
        ax=axes[1, 0],
        color="tab:red",
        linewidth=2.0,
        label=f"Rolling mean ({config.rolling_window})",
    )
    axes[1, 0].axhline(0.0, color="black", linestyle="--")
    axes[1, 0].set_title("Read-Write Error Over Time")
    axes[1, 0].set_xlabel("Sample")
    axes[1, 0].set_ylabel("x_recv - x_trans")
    axes[1, 0].legend()

    axes[1, 1].hist(
        metrics["absolute_gap"].dropna(),
        bins=min(50, max(10, len(metrics) // 5)),
        color="tab:purple",
        alpha=0.8,
    )
    axes[1, 1].set_title("Absolute Error Histogram")
    axes[1, 1].set_xlabel("|x_recv - x_trans|")
    axes[1, 1].set_ylabel("Count")

    save_figure(figure, config.output_dir / "consistency_analysis.png", config.show_plots)


def plot_realtime_deviation(metrics: pd.DataFrame, config: AnalysisConfig) -> None:
    """Plot deviation from the configured real-time period."""
    figure, axes = plt.subplots(2, 2, figsize=(16, 10))
    figure.suptitle("Cycle Duration and Jitter", fontsize=16)

    metrics["cycle_duration_us"].dropna().plot(ax=axes[0, 0], color="tab:blue", alpha=0.75)
    metrics["cycle_duration_us"].rolling(config.rolling_window).mean().plot(
        ax=axes[0, 0],
        color="tab:red",
        linewidth=2.0,
        label=f"Rolling mean ({config.rolling_window})",
    )
    axes[0, 0].axhline(config.target_cycle_us, color="black", linestyle="--", label="Target")
    axes[0, 0].set_title("Cycle Duration")
    axes[0, 0].set_xlabel("Sample")
    axes[0, 0].set_ylabel("Cycle Duration (us)")
    axes[0, 0].legend()

    metrics["jitter_us"].dropna().plot(ax=axes[0, 1], color="tab:red", alpha=0.75)
    metrics["jitter_us"].rolling(config.rolling_window).mean().plot(
        ax=axes[0, 1],
        color="tab:blue",
        linewidth=2.0,
        label=f"Rolling mean ({config.rolling_window})",
    )
    axes[0, 1].axhline(0.0, color="black", linestyle="--", label="Ideal")
    axes[0, 1].set_title("Jitter Relative to Target")
    axes[0, 1].set_xlabel("Sample")
    axes[0, 1].set_ylabel("Jitter (us)")
    axes[0, 1].legend()

    axes[1, 0].hist(
        metrics["cycle_duration_us"].dropna(),
        bins=min(50, max(10, len(metrics) // 5)),
        color="tab:green",
        alpha=0.8,
    )
    axes[1, 0].set_title("Cycle Duration Histogram")
    axes[1, 0].set_xlabel("Cycle Duration (us)")
    axes[1, 0].set_ylabel("Count")

    axes[1, 1].hist(
        metrics["jitter_us"].dropna(),
        bins=min(50, max(10, len(metrics) // 5)),
        color="tab:cyan",
        alpha=0.8,
    )
    axes[1, 1].set_title("Jitter Histogram")
    axes[1, 1].set_xlabel("Jitter (us)")
    axes[1, 1].set_ylabel("Count")

    save_figure(figure, config.output_dir / "realtime_deviation.png", config.show_plots)


def build_summary(metrics: pd.DataFrame, config: AnalysisConfig) -> str:
    """Create a concise text summary for terminal output."""
    end_to_end: pd.Series = metrics["end_to_end_latency_us"].dropna()
    cycle_duration: pd.Series = metrics["cycle_duration_us"].dropna()
    absolute_gap: pd.Series = metrics["absolute_gap"].dropna()
    jitter: pd.Series = metrics["jitter_us"].dropna()
    sleep_after_receive: pd.Series = metrics["sleep_after_receive_us"].dropna()
    deadline_misses: int = int(metrics["deadline_miss"].fillna(False).sum())
    negative_slack: int = int(metrics["negative_slack"].fillna(False).sum())
    sample_count: int = len(metrics)
    deadline_miss_rate: float = (
        deadline_misses / sample_count * 100.0 if sample_count else 0.0
    )
    negative_slack_rate: float = (
        negative_slack / sample_count * 100.0 if sample_count else 0.0
    )

    return "\n".join(
        [
            "Trace analysis summary",
            f"Samples: {sample_count}",
            (
                "End-to-end latency (us): "
                f"mean={end_to_end.mean():.3f}, p95={end_to_end.quantile(0.95):.3f}, "
                f"max={end_to_end.max():.3f}"
            ),
            (
                "Deadline misses: "
                f"{deadline_misses}/{sample_count} ({deadline_miss_rate:.6f}%) with "
                f"end_to_end_latency_us > {config.target_cycle_us:.3f}"
            ),
            (
                "Cycle duration (us): "
                f"mean={cycle_duration.mean():.3f}, std={cycle_duration.std():.3f}, "
                f"target={config.target_cycle_us:.3f}"
            ),
            (
                "Jitter (us): "
                f"mean={jitter.mean():.3f}, p95_abs={jitter.abs().quantile(0.95):.3f}, "
                f"min={jitter.min():.3f}, max={jitter.max():.3f}"
            ),
            (
                "Consistency absolute error: "
                f"mean={absolute_gap.mean():.6f}, p95={absolute_gap.quantile(0.95):.6f}, "
                f"max={absolute_gap.max():.6f}"
            ),
            (
                "Sleep after receive (us): "
                f"mean={sleep_after_receive.mean():.3f}, "
                f"p95={sleep_after_receive.quantile(0.95):.3f}, "
                f"min={sleep_after_receive.min():.3f}"
            ),
            (
                "Negative slack samples: "
                f"{negative_slack}/{sample_count} ({negative_slack_rate:.6f}%) with "
                "sleep_after_receive_us <= 0"
            ),
            f"Plots written to: {config.output_dir}",
        ]
    )


def run(config: AnalysisConfig) -> None:
    """Execute the full analysis pipeline."""
    config.output_dir.mkdir(parents=True, exist_ok=True)

    trace: pd.DataFrame = load_trace(config.input_csv)
    metrics: pd.DataFrame = compute_metrics(
        trace, config.target_cycle_us, config.input_time_unit
    )

    plot_latency(metrics, config)
    plot_consistency(metrics, config)
    plot_realtime_deviation(metrics, config)

    print(build_summary(metrics, config))


def main() -> None:
    """CLI entrypoint."""
    config: AnalysisConfig = parse_args()
    run(config)


if __name__ == "__main__":
    main()
