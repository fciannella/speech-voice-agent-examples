#!/bin/bash

# Configuration variables
HOST="0.0.0.0"  # Default host
PORT=8100             # Default port
NUM_CLIENTS=1         # Default number of parallel clients
BASE_OUTPUT_DIR="./results"
TEST_DURATION=150      # Default test duration in seconds
CLIENT_START_DELAY=1  # Delay between client starts in seconds
THRESHOLD=0.5         # Default threshold for filtered average latency

# Generate timestamp for unique directory
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTPUT_DIR="${BASE_OUTPUT_DIR}_${TIMESTAMP}"
SUMMARY_FILE="$OUTPUT_DIR/summary.json"

# Process command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --host)
      HOST="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --clients)
      NUM_CLIENTS="$2"
      shift 2
      ;;
    --output-dir)
      BASE_OUTPUT_DIR="$2"
      OUTPUT_DIR="${BASE_OUTPUT_DIR}_${TIMESTAMP}"
      SUMMARY_FILE="$OUTPUT_DIR/summary.json"
      shift 2
      ;;
    --test-duration)
      TEST_DURATION="$2"
      shift 2
      ;;
    --client-start-delay)
      CLIENT_START_DELAY="$2"
      shift 2
      ;;
    --threshold)
      THRESHOLD="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--host HOST] [--port PORT] [--clients NUM_CLIENTS] [--output-dir DIR] [--test-duration SECONDS] [--client-start-delay SECONDS] [--threshold SECONDS]"
      exit 1
      ;;
  esac
done

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

echo "=== ACE Controller Multi-Client Benchmark (Staggered Start) ==="
echo "Host: $HOST"
echo "Port: $PORT"
echo "Number of clients: $NUM_CLIENTS"
echo "Client start delay: $CLIENT_START_DELAY seconds"
echo "Test duration: $TEST_DURATION seconds"
echo "Latency threshold: $THRESHOLD seconds"
echo "Output directory: $OUTPUT_DIR"
echo "================================================================"

# Calculate timing
# All clients will start within (NUM_CLIENTS - 1) * CLIENT_START_DELAY seconds
# Metrics collection will start after the last client starts
TOTAL_START_TIME=$(( (NUM_CLIENTS - 1) * CLIENT_START_DELAY ))
METRICS_START_TIME=$(date +%s)
METRICS_START_TIME=$((METRICS_START_TIME + TOTAL_START_TIME))  # Set to when the last client starts

# Run clients with staggered starts
pids=()

for ((i=1; i<=$NUM_CLIENTS; i++)); do
  # Generate a unique stream ID for each client
  STREAM_ID="client_${i}_$(date +%s%N | cut -b1-13)"
  
  # Calculate start delay for this client (0 for first client, increasing for others)
  START_DELAY=$(( (i - 1) * CLIENT_START_DELAY ))
  
  # Run client in background with appropriate delays
  python ./file_input_client.py \
    --stream-id "$STREAM_ID" \
    --host "$HOST" \
    --port "$PORT" \
    --output-dir "$OUTPUT_DIR" \
    --start-delay "$START_DELAY" \
    --metrics-start-time "$METRICS_START_TIME" \
    --test-duration "$TEST_DURATION" \
    --threshold "$THRESHOLD" > "$OUTPUT_DIR/client_${i}.log" 2>&1 &
  
  # Store the process ID
  pids+=($!)
  
  # Small delay to ensure proper process creation
  sleep 0.1
done

echo ""
echo "Timing plan:"
echo "- First client starts immediately"
echo "- Last client starts in $TOTAL_START_TIME seconds"
echo "- Metrics collection starts at $(date -d @$METRICS_START_TIME)"
echo "- Test will run for $TEST_DURATION seconds after metrics collection starts"
echo "- Expected completion time: $(date -d @$((METRICS_START_TIME + TEST_DURATION)))"
echo ""

# Wait for all clients to finish
for pid in "${pids[@]}"; do
  wait "$pid"
done

# Calculate aggregate statistics across all clients
TOTAL_LATENCY=0
TOTAL_TURNS=0
CLIENT_COUNT=0
MIN_LATENCY=9999
MAX_LATENCY=0

# Variables for filtered latency statistics
TOTAL_FILTERED_LATENCY=0
TOTAL_FILTERED_TURNS=0
CLIENTS_WITH_FILTERED=0
MIN_FILTERED_LATENCY=9999
MAX_FILTERED_LATENCY=0

# Array to store all client average latencies for p95 calculation
CLIENT_LATENCIES=()
CLIENT_FILTERED_LATENCIES=()

# Arrays to track glitch detection
CLIENTS_WITH_GLITCHES=()
TOTAL_GLITCH_COUNT=0

# Variables to track reverse barge-in detection
TOTAL_REVERSE_BARGE_INS=0
CLIENT_REVERSE_BARGE_INS=()
CLIENTS_WITH_REVERSE_BARGE_INS=0

# Function to calculate p95 from an array of values
calculate_p95() {
  local values=("$@")
  local count=${#values[@]}
  
  if [ $count -eq 0 ]; then
    echo "0"
    return
  fi
  
  # Sort the array (using a simple bubble sort for bash compatibility)
  for ((i = 0; i < count; i++)); do
    for ((j = i + 1; j < count; j++)); do
      if (( $(echo "${values[i]} > ${values[j]}" | bc -l) )); then
        temp=${values[i]}
        values[i]=${values[j]}
        values[j]=$temp
      fi
    done
  done
  
  # Calculate p95 index 
  local p95_index=$(echo "scale=0; ($count - 1) * 0.95" | bc -l | cut -d'.' -f1)
  
  # Ensure index is within bounds
  if [ $p95_index -ge $count ]; then
    p95_index=$((count - 1))
  fi
  
  echo "${values[$p95_index]}"
}

# Process all result files
for result_file in "$OUTPUT_DIR"/latency_results_*.json; do
  if [ -f "$result_file" ]; then
    # Extract data using jq if available, otherwise use awk as fallback
    if command -v jq &> /dev/null; then
      AVG_LATENCY=$(jq '.average_latency' "$result_file")
      FILTERED_AVG_LATENCY=$(jq '.filtered_average_latency' "$result_file")
      NUM_TURNS=$(jq '.num_turns' "$result_file")
      NUM_FILTERED_TURNS=$(jq '.num_filtered_turns' "$result_file")
      STREAM_ID=$(jq -r '.stream_id' "$result_file")
      GLITCH_DETECTED=$(jq '.glitch_detected' "$result_file")
      REVERSE_BARGE_INS_COUNT=$(jq '.reverse_barge_ins_count' "$result_file")
    else
      # Fallback to grep and basic string processing
      AVG_LATENCY=$(grep -o '"average_latency": [0-9.]*' "$result_file" | cut -d' ' -f2)
      FILTERED_AVG_LATENCY=$(grep -o '"filtered_average_latency": [0-9.]*' "$result_file" | cut -d' ' -f2)
      NUM_TURNS=$(grep -o '"num_turns": [0-9]*' "$result_file" | cut -d' ' -f2)
      NUM_FILTERED_TURNS=$(grep -o '"num_filtered_turns": [0-9]*' "$result_file" | cut -d' ' -f2)
      STREAM_ID=$(grep -o '"stream_id": "[^"]*"' "$result_file" | cut -d'"' -f4)
      GLITCH_DETECTED=$(grep -o '"glitch_detected": [a-z]*' "$result_file" | cut -d' ' -f2)
      REVERSE_BARGE_INS_COUNT=$(grep -o '"reverse_barge_ins_count": [0-9]*' "$result_file" | cut -d' ' -f2)
    fi
    
    echo "Client $STREAM_ID: Average latency = $AVG_LATENCY seconds over $NUM_TURNS turns"
    
    # Display filtered latency information
    if [ "$FILTERED_AVG_LATENCY" != "null" ] && [ -n "$FILTERED_AVG_LATENCY" ]; then
      echo "  Filtered Average latency (>$THRESHOLD s) = $FILTERED_AVG_LATENCY seconds over $NUM_FILTERED_TURNS turns"
      
      # Add to filtered latency statistics
      TOTAL_FILTERED_LATENCY=$(echo "$TOTAL_FILTERED_LATENCY + $FILTERED_AVG_LATENCY" | bc -l)
      TOTAL_FILTERED_TURNS=$((TOTAL_FILTERED_TURNS + NUM_FILTERED_TURNS))
      CLIENTS_WITH_FILTERED=$((CLIENTS_WITH_FILTERED + 1))
      CLIENT_FILTERED_LATENCIES+=($FILTERED_AVG_LATENCY)
      
      # Update min/max filtered latency
      if (( $(echo "$FILTERED_AVG_LATENCY < $MIN_FILTERED_LATENCY" | bc -l) )); then
        MIN_FILTERED_LATENCY=$FILTERED_AVG_LATENCY
      fi
      
      if (( $(echo "$FILTERED_AVG_LATENCY > $MAX_FILTERED_LATENCY" | bc -l) )); then
        MAX_FILTERED_LATENCY=$FILTERED_AVG_LATENCY
      fi
    else
      echo "  No latencies above $THRESHOLD s threshold"
    fi
    
    # Check for glitch detection
    if [ "$GLITCH_DETECTED" = "true" ]; then
      echo "  ⚠️  Audio glitches detected in client $STREAM_ID"
      CLIENTS_WITH_GLITCHES+=("$STREAM_ID")
      TOTAL_GLITCH_COUNT=$((TOTAL_GLITCH_COUNT + 1))
    fi

    # Display and track reverse barge-in count
    if [ -n "$REVERSE_BARGE_INS_COUNT" ] && [ "$REVERSE_BARGE_INS_COUNT" -gt 0 ]; then
      echo "  Reverse barge-ins detected: $REVERSE_BARGE_INS_COUNT occurrences"
      CLIENT_REVERSE_BARGE_INS+=("$STREAM_ID")
      CLIENTS_WITH_REVERSE_BARGE_INS=$((CLIENTS_WITH_REVERSE_BARGE_INS + 1))
    fi
    
    # Add to total reverse barge-in count
    if [ -n "$REVERSE_BARGE_INS_COUNT" ]; then
      TOTAL_REVERSE_BARGE_INS=$((TOTAL_REVERSE_BARGE_INS + REVERSE_BARGE_INS_COUNT))
    fi
    
    # Add to array for p95 calculation
    CLIENT_LATENCIES+=($AVG_LATENCY)
    
    # Update aggregate statistics
    TOTAL_LATENCY=$(echo "$TOTAL_LATENCY + $AVG_LATENCY" | bc -l)
    TOTAL_TURNS=$((TOTAL_TURNS + NUM_TURNS))
    CLIENT_COUNT=$((CLIENT_COUNT + 1))
    
    # Update min/max latency
    if (( $(echo "$AVG_LATENCY < $MIN_LATENCY" | bc -l) )); then
      MIN_LATENCY=$AVG_LATENCY
    fi
    
    if (( $(echo "$AVG_LATENCY > $MAX_LATENCY" | bc -l) )); then
      MAX_LATENCY=$AVG_LATENCY
    fi
  fi
done

# Calculate overall statistics
if [ $CLIENT_COUNT -gt 0 ]; then
  AGGREGATE_AVG_LATENCY=$(echo "scale=3; $TOTAL_LATENCY / $CLIENT_COUNT" | bc -l)
  P95_CLIENT_LATENCY=$(calculate_p95 "${CLIENT_LATENCIES[@]}")
  
  # Calculate filtered statistics
  AGGREGATE_FILTERED_AVG_LATENCY="null"
  P95_FILTERED_CLIENT_LATENCY="null"
  
  if [ $CLIENTS_WITH_FILTERED -gt 0 ]; then
    AGGREGATE_FILTERED_AVG_LATENCY=$(echo "scale=3; $TOTAL_FILTERED_LATENCY / $CLIENTS_WITH_FILTERED" | bc -l)
    P95_FILTERED_CLIENT_LATENCY=$(calculate_p95 "${CLIENT_FILTERED_LATENCIES[@]}")
  fi
  
  echo "=============================================="
  echo "BENCHMARK SUMMARY (Staggered Start)"
  echo "=============================================="
  echo "Total clients: $CLIENT_COUNT"
  echo "Latency threshold: $THRESHOLD seconds"
  echo ""
  echo "STANDARD LATENCY STATISTICS:"
  echo "Average latency across all clients: $AGGREGATE_AVG_LATENCY seconds"
  echo "P95 latency across client averages: $P95_CLIENT_LATENCY seconds"
  echo "Minimum client average latency: $MIN_LATENCY seconds"
  echo "Maximum client average latency: $MAX_LATENCY seconds"
  echo ""
  echo "FILTERED LATENCY STATISTICS (>$THRESHOLD s):"
  if [ "$AGGREGATE_FILTERED_AVG_LATENCY" != "null" ]; then
    echo "Clients with filtered data: $CLIENTS_WITH_FILTERED out of $CLIENT_COUNT"
    echo "Average filtered latency: $AGGREGATE_FILTERED_AVG_LATENCY seconds"
    echo "P95 filtered latency: $P95_FILTERED_CLIENT_LATENCY seconds"
    echo "Minimum client filtered latency: $MIN_FILTERED_LATENCY seconds"
    echo "Maximum client filtered latency: $MAX_FILTERED_LATENCY seconds"
  else
    echo "No latencies above $THRESHOLD s threshold found across all clients"
  fi
  echo ""
  echo "AUDIO GLITCH DETECTION:"
  if [ $TOTAL_GLITCH_COUNT -gt 0 ]; then
    echo "⚠️  Audio glitches detected in $TOTAL_GLITCH_COUNT out of $CLIENT_COUNT clients"
    echo "Affected clients:"
    for client in "${CLIENTS_WITH_GLITCHES[@]}"; do
      echo "  - $client"
    done
  else
    echo "✅ No audio glitches detected in any client"
  fi

  echo "REVERSE BARGE-IN DETECTION:"
  if [ $TOTAL_REVERSE_BARGE_INS -gt 0 ]; then
    echo "Total reverse barge-ins detected: $TOTAL_REVERSE_BARGE_INS occurrences"
    echo "Clients with reverse barge-ins: $CLIENTS_WITH_REVERSE_BARGE_INS out of $CLIENT_COUNT"
    if [ $CLIENTS_WITH_REVERSE_BARGE_INS -gt 0 ]; then
      echo "Affected clients:"
      for client in "${CLIENT_REVERSE_BARGE_INS[@]}"; do
        echo "  - $client"
      done
    fi
  else
    echo "✅ No reverse barge-ins detected in any client"
  fi

  echo ""
  echo "ERROR DETECTION:"
  # Initialize arrays for error tracking
  declare -A CLIENT_ERROR_COUNTS
  CLIENTS_WITH_ERRORS=0
  TOTAL_ERRORS=0

  # Process logs for each client to find errors
  for ((i=1; i<=$NUM_CLIENTS; i++)); do
    LOG_FILE="$OUTPUT_DIR/client_${i}.log"
    if [ -f "$LOG_FILE" ]; then
      ERROR_COUNT=$(grep -c "^\[ERROR\]" "$LOG_FILE")
      if [ $ERROR_COUNT -gt 0 ]; then
        CLIENTS_WITH_ERRORS=$((CLIENTS_WITH_ERRORS + 1))
        TOTAL_ERRORS=$((TOTAL_ERRORS + ERROR_COUNT))
        CLIENT_ERROR_COUNTS["client_${i}"]=$ERROR_COUNT
        
        echo "⚠️  Client ${i} errors ($ERROR_COUNT):"
        grep "^\[ERROR\]" "$LOG_FILE" | sed 's/^/  /'
      fi
    fi
  done

  if [ $TOTAL_ERRORS -eq 0 ]; then
    echo "✅ No errors detected in any client"
  else
    echo "⚠️  Total errors across all clients: $TOTAL_ERRORS"
    echo "⚠️  Clients with errors: $CLIENTS_WITH_ERRORS out of $CLIENT_COUNT"
  fi
  
  # Create summary JSON
  cat > "$SUMMARY_FILE" << EOF
{
  "timestamp": "$(date -Iseconds)",
  "config": {
    "host": "$HOST",
    "port": $PORT,
    "num_clients": $NUM_CLIENTS,
    "client_start_delay": $CLIENT_START_DELAY,
    "test_duration": $TEST_DURATION,
    "threshold": $THRESHOLD,
    "metrics_start_time": $METRICS_START_TIME
  },
  "results": {
    "total_clients": $CLIENT_COUNT,
    "total_turns": $TOTAL_TURNS,
    "aggregate_average_latency": $AGGREGATE_AVG_LATENCY,
    "p95_client_latency": $P95_CLIENT_LATENCY,
    "min_client_latency": $MIN_LATENCY,
    "max_client_latency": $MAX_LATENCY,
    "filtered_results": {
      "clients_with_filtered_data": $CLIENTS_WITH_FILTERED,
      "total_filtered_turns": $TOTAL_FILTERED_TURNS,
      "aggregate_filtered_average_latency": $AGGREGATE_FILTERED_AVG_LATENCY,
      "p95_filtered_client_latency": $P95_FILTERED_CLIENT_LATENCY,
      "min_filtered_client_latency": $([ "$AGGREGATE_FILTERED_AVG_LATENCY" != "null" ] && echo "$MIN_FILTERED_LATENCY" || echo "null"),
      "max_filtered_client_latency": $([ "$AGGREGATE_FILTERED_AVG_LATENCY" != "null" ] && echo "$MAX_FILTERED_LATENCY" || echo "null")
    },
    "glitch_detection": {
      "clients_with_glitches": $TOTAL_GLITCH_COUNT,
      "total_clients": $CLIENT_COUNT,
      "affected_client_ids": [$(printf '"%s",' "${CLIENTS_WITH_GLITCHES[@]}" | sed 's/,$//')]
    },
    "reverse_barge_in_detection": {
      "total_clients": $CLIENT_COUNT,
      "total_reverse_barge_ins": $TOTAL_REVERSE_BARGE_INS,
      "clients_with_reverse_barge_ins": $CLIENTS_WITH_REVERSE_BARGE_INS,
      "affected_client_ids": [$(printf '"%s",' "${CLIENT_REVERSE_BARGE_INS[@]}" | sed 's/,$//')]
    },
    "error_detection": {
      "total_clients": $CLIENT_COUNT,
      "total_errors": $TOTAL_ERRORS,
      "clients_with_errors": $CLIENTS_WITH_ERRORS,
      "client_error_counts": {
        $(for client in "${!CLIENT_ERROR_COUNTS[@]}"; do
          printf '"%s": %d,\n        ' "$client" "${CLIENT_ERROR_COUNTS[$client]}"
        done | sed 's/,\s*$//')
      }
    }
  }
}
EOF
  
  echo "Summary saved to: $SUMMARY_FILE"
else
  echo "No valid result files found!"
fi

echo "Benchmark complete." 