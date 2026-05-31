#!/usr/bin/env bash
set -euo pipefail

# Configuration
PORT=10005
PID=""
LOG_FILE="verify.log"

echo "=== Snowflake Cortex Search Mitigation Verification ==="
echo "Logging output to $LOG_FILE"
echo "" > "$LOG_FILE"

# Clean up function
cleanup() {
    if [ -n "${PID:-}" ]; then
        echo "Stopping validation engine (PID: $PID)..."
        kill "$PID" 2>/dev/null || true
    fi
    # Deactivate venv
    if [ -n "${VIRTUAL_ENV:-}" ]; then
        deactivate || true
    fi
    # Remove temporary database
    if [ -f "cortex_simulator.db" ]; then
        rm "cortex_simulator.db"
    fi
}
trap cleanup EXIT

# 1. Virtual Environment Setup
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment in .venv..."
    python3 -m venv .venv >> "$LOG_FILE" 2>&1
fi

echo "Activating virtual environment..."
# shellcheck disable=SC1091
source .venv/bin/activate

echo "Installing Python dependencies (fastapi, uvicorn, pydantic, hypothesis, diagrams, requests, httpx)..."
pip install --upgrade pip >> "$LOG_FILE" 2>&1
pip install fastapi uvicorn pydantic hypothesis diagrams requests httpx >> "$LOG_FILE" 2>&1

# Ensure database is clean
if [ -f "cortex_simulator.db" ]; then
    rm "cortex_simulator.db"
fi

# 2. Run Diagram Generator
echo "Running diagram generator (generate_architecture.py)..."
python3 generate_architecture.py >> "$LOG_FILE" 2>&1 || {
    echo "Warning: Diagram generation returned non-zero code. Check verify.log."
}

# 3. Spin up validate_engine.py
echo "Starting validation engine on port $PORT..."
python3 validate_engine.py >> "$LOG_FILE" 2>&1 &
PID=$!

# Wait for server to start
echo "Waiting for API to become active..."
for i in {1..30}; do
    if curl -s "http://127.0.0.1:$PORT/docs" > /dev/null; then
        echo "Validation engine active."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Server failed to start. View verify.log for details."
        exit 1
    fi
    sleep 0.5
done

# Helper function for curl tests
test_endpoint() {
    local description="$1"
    local path="$2"
    local token="$3"
    local expected_count="$4"
    
    echo -n "Test: $description... "
    
    local headers=()
    if [ -n "$token" ]; then
        headers=(-H "Authorization: Bearer $token")
    fi
    
    local response
    response=$(curl -s -X GET "http://127.0.0.1:$PORT$path" "${headers[@]}")
    
    # Check length of the JSON array
    local count
    count=$(echo "$response" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
    
    if [ "$count" -eq "$expected_count" ]; then
        echo "PASS (Found $count elements)"
    else
        echo "FAIL (Expected $expected_count, got $count)"
        echo "Response: $response"
        exit 1
    fi
}

echo ""
echo "--- Running Zero-Trust Token Verification Scenarios ---"

# Scenario A: Public user querying sensitive data (pre-filter mode) -> Must return 0
test_endpoint "Public User searching sensitive 'strategy' (Pre-Filter)" \
              "/search?q=strategy&filter_mode=pre-filter" \
              "token-public" 0

# Scenario B: Public user querying public data -> Must return 2 (Cortex Overview & Public Knowledgebase)
test_endpoint "Public User searching public data (Pre-Filter)" \
              "/search?q=public&filter_mode=pre-filter" \
              "token-public" 2

# Scenario C: Finance user querying strategy -> Must return 2 (M&A Strategy & Q3 Financial Strategy)
test_endpoint "Finance User searching 'strategy' (Pre-Filter)" \
              "/search?q=strategy&filter_mode=pre-filter" \
              "token-finance" 2

# Scenario D: Unmitigated Owner Rights Leak (no-filter mode)
test_endpoint "VULNERABILITY DEMO: Public User searching 'strategy' (No-Filter Leak)" \
              "/search?q=strategy&filter_mode=no-filter" \
              "token-public" 2

# Scenario E: KNN Dilution Demonstration (post-filter mode)
test_endpoint "Dilution Demo: Public User querying '*' (Post-Filter Dilution)" \
              "/search?q=*&filter_mode=post-filter" \
              "token-public" 0

test_endpoint "Dilution Contrast: Public User querying '*' (Pre-Filter Correctness)" \
              "/search?q=*&filter_mode=pre-filter" \
              "token-public" 2

echo ""
echo "--- Running Hypothesis Property-Based Fuzzing Tests ---"
python3 test_fuzz.py

echo ""
echo "=== All Verification Assertions and Fuzzing Invariants PASSED successfully ==="
