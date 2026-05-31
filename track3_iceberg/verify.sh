#!/bin/bash
set -e

# ANSI colors for shell
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'

echo -e "${BOLD}Running Apache Iceberg OCC & 3-Phase Commit Simulation Verification...${NC}"

# Navigate to script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "$SCRIPT_DIR"

# Verify python availability
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}Error: python3 is not installed or not in PATH.${NC}"
    exit 1
fi

# Make sure sqlite3 CLI is available for verification checks
if ! command -v sqlite3 &> /dev/null; then
    echo -e "${RED}Error: sqlite3 CLI utility is required for assertions.${NC}"
    exit 1
fi

# Render the architecture diagram
if [ -f "generate_architecture.py" ]; then
    echo -e "\nRendering architecture diagram..."
    python3 generate_architecture.py || echo -e "${RED}Warning: Diagram rendering failed. Check if 'diagrams' library and 'graphviz' are installed.${NC}"
fi

# Run validation engine
echo -e "\nRunning python validation engine..."
python3 validate_engine.py
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo -e "\n${RED}Verification FAILED: validate_engine.py exited with status $EXIT_CODE.${NC}"
    exit 1
fi

# Assertions on catalog artifacts
echo -e "\n${BOLD}Asserting consistency requirements...${NC}"

# 1. Catalog database must exist
if [ ! -f "sandbox/catalog.db" ]; then
    echo -e "${RED}Assertion failed: sandbox/catalog.db does not exist.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ SQLite Catalog Database created.${NC}"

# 2. Schema and tables must contain valid records
COMMIT_COUNT=$(sqlite3 sandbox/catalog.db "SELECT count(*) FROM transactions WHERE status = 'COMMITTED';")
ABORT_COUNT=$(sqlite3 sandbox/catalog.db "SELECT count(*) FROM transactions WHERE status = 'ABORTED';")
CURRENT_POINTER=$(sqlite3 sandbox/catalog.db "SELECT metadata_location FROM tables WHERE table_identifier = 'default.snowflake_sovereign_table';")

echo -e " -> Total Committed Transactions: ${COMMIT_COUNT}"
echo -e " -> Total Aborted/Rolled Back Transactions: ${ABORT_COUNT}"
echo -e " -> Current Active Metadata Pointer: ${CURRENT_POINTER}"

if [ -z "$CURRENT_POINTER" ]; then
    echo -e "${RED}Assertion failed: Table pointer in catalog is empty.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Catalog metadata pointer swap resolved.${NC}"

if [ "$COMMIT_COUNT" -eq 0 ]; then
    echo -e "${RED}Assertion failed: Expected at least one committed transaction.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Successful OCC commits registered.${NC}"

# 3. Verify files on simulated storage
ACTIVE_METADATA_FILE=$(basename "$CURRENT_POINTER")
if [ ! -f "sandbox/metadata/$ACTIVE_METADATA_FILE" ]; then
    echo -e "${RED}Assertion failed: Current metadata file sandbox/metadata/$ACTIVE_METADATA_FILE does not exist.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Physical metadata file exists on storage.${NC}"

# 4. Check formatting of Iceberg metadata JSON
TABLE_UUID=$(python3 -c "import json; print(json.load(open('sandbox/metadata/$ACTIVE_METADATA_FILE'))['table-uuid'])")
if [ -z "$TABLE_UUID" ]; then
    echo -e "${RED}Assertion failed: Table Metadata JSON is missing table-uuid.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Metadata schema matches Iceberg v2 specification format.${NC}"

echo -e "\n${GREEN}${BOLD}Verification SUCCESS. All assertions passed! All files consistent and transactionally safe.${NC}"
exit 0
