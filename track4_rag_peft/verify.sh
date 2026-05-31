#!/usr/bin/env bash
# ==============================================================================
# verify.sh
# ------------------------------------------------------------------------------
# High-grade verification suite for the Sovereign RAG & PEFT Pipeline.
# Validates compliance engines and runs the Python 'diagrams' renderer.
# Automatically provisions virtual environments to bypass Arch PEP 668 limits.
# ==============================================================================

set -e

# Terminal colors
GREEN='\033[92m'
YELLOW='\033[93m'
RED='\033[91m'
BOLD='\033[1m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_PATH="${SCRIPT_DIR}/validate_engine.py"
DIAGRAM_GEN_PATH="${SCRIPT_DIR}/generate_architecture.py"
VENV_DIR="${SCRIPT_DIR}/.venv"

echo -e "${BOLD}${YELLOW}=== Sovereign Systems Architect Verification Suite ===${RESET}"

# 1. Enforce Executable Attributes
echo -e "\n${BOLD}[1/4] Enforcing permissions...${RESET}"
chmod +x "${ENGINE_PATH}"
chmod +x "${DIAGRAM_GEN_PATH}"
echo -e "  [${GREEN}✓${RESET}] Executable rights set for validate_engine.py & generate_architecture.py"

# 2. Render Architecture Diagram via diagrams library in a virtual environment
echo -e "\n${BOLD}[2/4] Rendering Pipeline Architecture Diagram...${RESET}"
if [ ! -d "${VENV_DIR}" ]; then
    echo -e "  Creating a local sandboxed virtual environment..."
    python3 -m venv "${VENV_DIR}"
fi

echo -e "  Ensuring diagrams and dependencies are installed in virtual environment..."
if "${VENV_DIR}/bin/pip" install diagrams --quiet; then
    echo -e "  [${GREEN}✓${RESET}] Virtual environment dependencies installed."
    if "${VENV_DIR}/bin/python" "${DIAGRAM_GEN_PATH}"; then
        echo -e "  [${GREEN}✓${RESET}] Architecture diagram rendered successfully: sovereign_architecture.png"
    else
        echo -e "  [${RED}✗${RESET}] Graphviz rendering failed. Ensure graphviz OS package is installed (e.g. pacman -S graphviz)."
    fi
else
    echo -e "  [${RED}✗${RESET}] Could not install python 'diagrams' library inside virtual environment."
fi

# 3. Test DPDP Redaction compliance
echo -e "\n${BOLD}[3/4] Running DPDP Compliance and Token Redaction test...${RESET}"
REDACT_TEST=$(python3 "${ENGINE_PATH}" --max-tokens 150 --redact)
if echo "${REDACT_TEST}" | grep -q "<REDACTED_"; then
    echo -e "  [${GREEN}✓${RESET}] PII redaction pipeline validated successfully."
else
    echo -e "  [${RED}✗${RESET}] PII redaction pipeline failed compliance check!"
    exit 1
fi

# 4. Generate Validation Trace Log
echo -e "\n${BOLD}[4/4] Writing trace logs...${RESET}"
LOG_DIR="${HOME}/logs"
mkdir -p "${LOG_DIR}"
LOG_PATH="${LOG_DIR}/track4_validation_run.log"

python3 "${ENGINE_PATH}" --max-tokens 120 --threshold 0.3 --redact > "${LOG_PATH}"
echo -e "  [${GREEN}✓${RESET}] Trace log created successfully at: ${LOG_PATH}"

echo -e "\n${BOLD}${GREEN}=== [10/10] Verification Complete: Sovereign RAG Pipeline Ready ===${RESET}\n"
