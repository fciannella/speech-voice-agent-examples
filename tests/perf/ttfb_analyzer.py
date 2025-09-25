#!/usr/bin/env python3
"""TTFB Log Analyzer.

Analyzes Time To First Byte (TTFB) logs, ASR compute latency, and LLM first sentence generation time
for multiple client streams and calculates average TTFB, ASR latency, first sentence time, and P95
for LLM, TTS, and ASR services.

Usage:
    python ttfb_analyzer.py [log_file_path]
    python ttfb_analyzer.py --help

Examples:
    python ttfb_analyzer.py
    python ttfb_analyzer.py /path/to/botlogs.log
    python ttfb_analyzer.py ../../examples/speech-to-speech/botlogs.log
"""

import argparse
import logging
import os
import re
import sys
from collections import defaultdict

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def calculate_p95(values: list[float]) -> float:
    """Calculate 95th percentile of values."""
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = int(0.95 * (len(sorted_values) - 1))
    return sorted_values[index]


def parse_logs(log_file_path: str) -> dict[str, dict[str, list[float]]]:
    """Parse LLM, TTS TTFBs, ASR compute latency, and LLM first sentence generation logs.

    Organize by client stream and service type. Only include events after the last client start.
    """
    data = defaultdict(lambda: {"LLM": [], "TTS": [], "ASR": [], "LLM_FIRST_SENTENCE": []})
    ttfb_pattern = r"streamId=([^\s]+)\s+-\s+(NvidiaLLMService|RivaTTSService)#\d+\s+TTFB:\s+([\d.]+)"
    asr_pattern = r"streamId=([^\s]+)\s+-\s+RivaASRService#\d+\s+ASR compute latency:\s+([\d.]+)"
    first_sentence_pattern = (
        r"streamId=([^\s]+)\s+-\s+NvidiaLLMService#\d+\s+LLM first sentence generation time:\s+([\d.]+)"
    )
    websocket_pattern = r".*Accepting WebSocket connection for stream ID client_\d+_\d+"

    # First pass: find the last client start log
    last_client_start_line = -1

    try:
        # Read all lines to find the last client start
        with open(log_file_path) as file:
            lines = file.readlines()

            # Find the last client start log by iterating through all lines
            for i, line in enumerate(lines):
                if re.search(websocket_pattern, line):
                    last_client_start_line = i

        # Validate that we found at least one client start
        if last_client_start_line == -1:
            logger.warning("No client start pattern found in logs")
            return dict()

        # Second pass: analyze only events after the last client start
        with open(log_file_path) as file:
            for i, line in enumerate(file):
                # Skip lines before the last client start
                if last_client_start_line != -1 and i <= last_client_start_line:
                    continue

                try:
                    # Check for TTFB metrics
                    ttfb_match = re.search(ttfb_pattern, line)
                    if ttfb_match:
                        client_id = ttfb_match.group(1).strip()
                        service_type = ttfb_match.group(2)
                        try:
                            ttfb_value = float(ttfb_match.group(3))
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid TTFB value in line {i + 1}: {ttfb_match.group(3)} - {e}")
                            continue

                        if service_type == "NvidiaLLMService":
                            data[client_id]["LLM"].append(ttfb_value)
                        elif service_type == "RivaTTSService":
                            data[client_id]["TTS"].append(ttfb_value)

                    # Check for ASR compute latency metrics
                    asr_match = re.search(asr_pattern, line)
                    if asr_match:
                        client_id = asr_match.group(1).strip()
                        try:
                            asr_latency = float(asr_match.group(2))
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid ASR latency value in line {i + 1}: {asr_match.group(2)} - {e}")
                            continue
                        data[client_id]["ASR"].append(asr_latency)

                    # Check for LLM first sentence generation time metrics
                    first_sentence_match = re.search(first_sentence_pattern, line)
                    if first_sentence_match:
                        client_id = first_sentence_match.group(1).strip()
                        try:
                            first_sentence_time = float(first_sentence_match.group(2))
                        except (ValueError, TypeError) as e:
                            logger.warning(
                                f"Invalid first sentence time value in line {i + 1}: "
                                f"{first_sentence_match.group(2)} - {e}"
                            )
                            continue
                        data[client_id]["LLM_FIRST_SENTENCE"].append(first_sentence_time)

                except Exception as e:
                    logger.warning(f"Error parsing line {i + 1}: {e}")
                    continue

    except FileNotFoundError:
        print(f"Error: Log file '{log_file_path}' not found.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading log file: {e}")
        sys.exit(1)

    return dict(data)


def calculate_client_averages(data: dict[str, dict[str, list[float]]]) -> dict[str, dict[str, float]]:
    """Calculate average metrics for each client and service type."""
    averages = {}
    for client_id, services in data.items():
        averages[client_id] = {}
        for service_type, values in services.items():
            if values:
                averages[client_id][service_type] = sum(values) / len(values)
            else:
                averages[client_id][service_type] = 0.0
    return averages


def print_results(data: dict[str, dict[str, list[float]]], client_averages: dict[str, dict[str, float]]):
    """Print analysis results."""
    print("=" * 90)
    print("LATENCY ANALYSIS RESULTS")
    print("=" * 90)

    # Show metric arrays for each client
    for client_id in sorted(data.keys()):
        llm_values = data[client_id]["LLM"]
        tts_values = data[client_id]["TTS"]
        asr_values = data[client_id]["ASR"]
        first_sentence_values = data[client_id]["LLM_FIRST_SENTENCE"]

        print(f"\n{client_id}:")
        print(f"  LLM TTFB: {[f'{v:.3f}' for v in llm_values]}")
        print(f"  TTS TTFB: {[f'{v:.3f}' for v in tts_values]}")
        print(f"  ASR Latency: {[f'{v:.3f}' for v in asr_values]}")
        print(f"  LLM First Sentence: {[f'{v:.3f}' for v in first_sentence_values]}")

    # Summary table with overall statistics
    print(
        f"\n{'Client ID':<25} {'LLM TTFB':<10} {'TTS TTFB':<10} {'ASR Lat':<10} "
        f"{'LLM 1st':<10} {'LLM calls':<10} {'TTS calls':<10} {'ASR calls':<10}"
    )
    print("-" * 120)

    for client_id in sorted(data.keys()):
        llm_avg = client_averages[client_id]["LLM"]
        tts_avg = client_averages[client_id]["TTS"]
        asr_avg = client_averages[client_id]["ASR"]
        first_sentence_avg = client_averages[client_id]["LLM_FIRST_SENTENCE"]
        llm_count = len(data[client_id]["LLM"])
        tts_count = len(data[client_id]["TTS"])
        asr_count = len(data[client_id]["ASR"])
        print(
            f"{client_id:<25} {llm_avg:<10.3f} {tts_avg:<10.3f} {asr_avg:<10.3f} {first_sentence_avg:<10.3f} "
            f"{llm_count:<10} {tts_count:<10} {asr_count:<10}"
        )

    # Calculate overall statistics across client averages
    llm_client_averages = [avg["LLM"] for avg in client_averages.values() if avg["LLM"] > 0]
    tts_client_averages = [avg["TTS"] for avg in client_averages.values() if avg["TTS"] > 0]
    asr_client_averages = [avg["ASR"] for avg in client_averages.values() if avg["ASR"] > 0]
    first_sentence_client_averages = [
        avg["LLM_FIRST_SENTENCE"] for avg in client_averages.values() if avg["LLM_FIRST_SENTENCE"] > 0
    ]

    # Add separator and overall statistics rows
    print("-" * 120)

    if llm_client_averages and tts_client_averages and asr_client_averages:
        llm_overall_avg = sum(llm_client_averages) / len(llm_client_averages)
        llm_p95 = calculate_p95(llm_client_averages)
        tts_overall_avg = sum(tts_client_averages) / len(tts_client_averages)
        tts_p95 = calculate_p95(tts_client_averages)
        asr_overall_avg = sum(asr_client_averages) / len(asr_client_averages)
        asr_p95 = calculate_p95(asr_client_averages)

        first_sentence_overall_avg = (
            sum(first_sentence_client_averages) / len(first_sentence_client_averages)
            if first_sentence_client_averages
            else 0.0
        )
        first_sentence_p95 = calculate_p95(first_sentence_client_averages) if first_sentence_client_averages else 0.0

        print(
            f"{'OVERALL AVERAGE':<25} {llm_overall_avg:<10.3f} {tts_overall_avg:<10.3f} "
            f"{asr_overall_avg:<10.3f} {first_sentence_overall_avg:<10.3f}"
        )
        print(f"{'OVERALL P95':<25} {llm_p95:<10.3f} {tts_p95:<10.3f} {asr_p95:<10.3f} {first_sentence_p95:<10.3f}")

    print("-" * 120)


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Analyze LLM, TTS TTFBs, ASR latency, and LLM first sentence generation time logs "
        "for multiple client streams"
    )
    parser.add_argument(
        "log_file",
        nargs="?",
        default="../../examples/speech-to-speech/botlogs.log",
        help="Path to log file (default: ../../examples/speech-to-speech/botlogs.log)",
    )
    args = parser.parse_args()

    print("Latency Log Analyzer")
    print(f"Analyzing: {args.log_file}")

    if not os.path.exists(args.log_file):
        print(f"Error: Log file '{args.log_file}' not found.")
        sys.exit(1)

    data = parse_logs(args.log_file)
    if not data:
        print("No performance data found in log file.")
        return

    print()

    client_averages = calculate_client_averages(data)
    print_results(data, client_averages)


if __name__ == "__main__":
    main()
