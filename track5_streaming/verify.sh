#!/usr/bin/env bash
# verify.sh
# Ingestion execution verification hook for low-latency streaming & egress optimization sandbox.

set -euo pipefail

# Define paths relative to the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"
ENGINE_SCRIPT="${SCRIPT_DIR}/validate_engine.py"
DIAGRAM_SCRIPT="${SCRIPT_DIR}/generate_architecture.py"

echo -e "\033[95m=== ECO Caching Routing Sandbox Verification ===\033[0m"

# 1. Verify existence of the scripts
if [ ! -f "${ENGINE_SCRIPT}" ]; then
    echo -e "\033[91m[-] Error: validate_engine.py not found at ${ENGINE_SCRIPT}\033[0m"
    exit 1
fi

if [ ! -f "${DIAGRAM_SCRIPT}" ]; then
    echo -e "\033[91m[-] Error: generate_architecture.py not found at ${DIAGRAM_SCRIPT}\033[0m"
    exit 1
fi

# 2. Make scripts executable
echo -e "\033[94m[+] Making scripts executable...\033[0m"
chmod +x "${ENGINE_SCRIPT}"
chmod +x "${DIAGRAM_SCRIPT}"

# 3. Render the Architecture Diagram
echo -e "\033[94m[+] Generating architecture diagram using Graphviz & Python diagrams...\033[0m"
"${VENV_PYTHON}" "${DIAGRAM_SCRIPT}"

# 4. Run the validation engine
echo -e "\033[94m[+] Launching local Python socket client-server simulation in venv...\033[0m"
"${VENV_PYTHON}" "${ENGINE_SCRIPT}"

# 5. Report success
echo -e "\033[92m[+] Verification simulation run complete.\033[0m"
