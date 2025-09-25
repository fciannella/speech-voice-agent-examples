# Performance Testing

This directory contains tools for evaluating the voice agent pipeline's latency and scalability/throughput under various loads. These tests simulate real-world scenarios where multiple users interact with the voice agent simultaneously.

## What the Tests Do

The performance tests:

- Open WebSocket clients that simulate user interactions
- Use pre-recorded audio files from `audio_files/` as user queries
- Send these queries to the voice agent pipeline and measure response times
- Track various latency metrics including end-to-end latency, component-wise breakdowns
- Can simulate multiple concurrent clients to test scaling
- Detect any audio glitches during processing

## Running Performance Tests

### 1. Start the Voice Agent Pipeline

First, start the voice agent pipeline and capture server logs for analysis.
See the prerequisites and setup instructions in `examples/speech-to-speech/README.md` before proceeding.

#### If Using Docker

From examples/speech-to-speech/ directory run:

```bash
# Start the services
docker compose up -d

# Capture logs and save them into a file
docker compose logs -f python-app > bot_logs_test1.txt 2>&1
```

Before starting a new performance run:

```bash
# Clear existing Docker logs
sudo truncate -s 0 /var/lib/docker/containers/$(docker compose ps -q python-app)/$(docker compose ps -q python-app)-json.log
```

#### If Using Python Environment

From examples/speech-to-speech/ directory run:

```bash
python bot.py > bot_logs_test1.txt 2>&1
```

### 2. Run the Multi-Client Benchmark

```bash
./run_multi_client_benchmark.sh --host 0.0.0.0 --port 8100 --clients 10 --test-duration 150
```

Parameters:

- `--host`: The host address (default: 0.0.0.0)
- `--port`: The port where your voice agent is running (default: 8100)
- `--clients`: Number of concurrent clients to simulate (default: 1)
- `--test-duration`: Duration of the test in seconds (default: 150)

The script will:

1. Start the specified number of concurrent clients
2. Simulate user interactions using audio files
3. Measure latencies and detect audio glitches
4. Save detailed results in the `results` directory as JSON files
5. Output a summary to the console

### 3. Analyze Component-wise Latency

After the benchmark completes, analyze the server logs for detailed latency breakdowns:

```bash
python ttfb_analyzer.py <relative_path_to_bot_logs_test1.txt>
```

This will show:

- Per-client latency metrics for LLM, TTS, and ASR components
- Number of calls made by each client
- Overall averages and P95 values
- Component-wise timing breakdowns

## Understanding the Results

The metrics measured include:

- **LLM TTFB**: Time to first byte from the LLM model
- **TTS TTFB**: Time to first byte from the TTS model
- **ASR Lat**: Compute latency of the ASR model
- **LLM 1st**: Time taken to generate first complete sentence from LLM
- **Calls**: Number of API calls made to each service

The results help identify:

- Performance bottlenecks in specific components
- Scaling behavior under concurrent load
- Potential audio quality issues
- Overall system responsiveness
