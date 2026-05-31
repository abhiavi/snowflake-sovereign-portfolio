#!/usr/bin/env python3
import os
import sys
import time
import json
import sqlite3
import threading
import random
import uuid
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

# ANSI colors for beautiful CLI output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Config paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SANDBOX_DIR = os.path.join(BASE_DIR, "sandbox")
DATA_DIR = os.path.join(SANDBOX_DIR, "data")
METADATA_DIR = os.path.join(SANDBOX_DIR, "metadata")
CATALOG_DB = os.path.join(SANDBOX_DIR, "catalog.db")

# Thread-safe logging
log_lock = threading.Lock()
def log(msg, color=Colors.ENDC, bold=False):
    timestamp = time.strftime("%H:%M:%S")
    prefix = f"[{timestamp}] "
    formatted_msg = f"{color}{Colors.BOLD if bold else ''}{prefix}{msg}{Colors.ENDC}"
    with log_lock:
        print(formatted_msg)
        sys.stdout.flush()

class IcebergCatalog:
    """
    Simulates an Iceberg REST Catalog using SQLite.
    Implements 3-Phase Commit (3PC) to update the catalog DB and storage metadata atomicity.
    Uses Row Locks and Status checks to verify Optimistic Concurrency Control (OCC).
    """
    def __init__(self):
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(CATALOG_DB)
        cursor = conn.cursor()
        # Catalog table store
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tables (
                table_identifier TEXT PRIMARY KEY,
                metadata_location TEXT
            )
        """)
        # Transaction log for 3PC status
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                tx_id TEXT PRIMARY KEY,
                table_identifier TEXT,
                status TEXT, -- PREPARED, PRECOMMITTED, COMMITTED, ABORTED
                proposed_metadata TEXT,
                previous_metadata TEXT,
                timestamp REAL
            )
        """)
        # Lock status table to avoid race conditions during 3PC coordination
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_locks (
                table_identifier TEXT PRIMARY KEY,
                locked_by_tx TEXT,
                lock_time REAL
            )
        """)
        conn.commit()
        conn.close()

    def get_table_metadata_pointer(self, table_id):
        conn = sqlite3.connect(CATALOG_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT metadata_location FROM tables WHERE table_identifier = ?", (table_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def initialize_table(self, table_id, initial_metadata_path):
        conn = sqlite3.connect(CATALOG_DB)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO tables (table_identifier, metadata_location) VALUES (?, ?)", 
                       (table_id, initial_metadata_path))
        conn.commit()
        conn.close()

    def execute_3pc_commit(self, table_id, tx_id, expected_metadata_path, new_metadata_path, fail_phase=None):
        """
        Coordinates a 3-Phase Commit (3PC):
        1. Phase 1: Can-Commit? (OCC Check + Table Lock)
        2. Phase 2: Pre-Commit (Write Metadata state to disk and log transaction status)
        3. Phase 3: Do-Commit (Update Catalog Pointer to new state)
        """
        conn = sqlite3.connect(CATALOG_DB)
        cursor = conn.cursor()

        try:
            # ========================================================
            # PHASE 1: CAN-COMMIT? (OCC Check and Resource Locking)
            # ========================================================
            log(f"[TX: {tx_id[:8]}] Phase 1 (Can-Commit) Started.", Colors.BLUE)
            
            # 1a. Verify Table Row Lock
            cursor.execute("SELECT locked_by_tx FROM active_locks WHERE table_identifier = ?", (table_id,))
            lock_row = cursor.fetchone()
            if lock_row:
                active_tx = lock_row[0]
                log(f"[TX: {tx_id[:8]}] Phase 1 FAIL: Table '{table_id}' is currently locked by active TX {active_tx[:8]}.", Colors.WARNING)
                raise sqlite3.OperationalError("Table locked by another concurrent transaction.")

            # 1b. OCC Validation: Check if table metadata pointer has changed since worker started
            cursor.execute("SELECT metadata_location FROM tables WHERE table_identifier = ?", (table_id,))
            current_row = cursor.fetchone()
            current_metadata = current_row[0] if current_row else None
            
            if current_metadata != expected_metadata_path:
                log(f"[TX: {tx_id[:8]}] Phase 1 FAIL (OCC Write Collision): Target metadata has updated from "
                    f"'{os.path.basename(expected_metadata_path or 'None')}' to "
                    f"'{os.path.basename(current_metadata or 'None')}' by a concurrent transaction.", Colors.WARNING)
                raise ValueError("OCC Write Collision detected. Transaction aborted.")

            # Lock the table row for 3PC sequence
            cursor.execute("INSERT INTO active_locks (table_identifier, locked_by_tx, lock_time) VALUES (?, ?, ?)",
                           (table_id, tx_id, time.time()))
            
            # Record TX status as PREPARED
            cursor.execute("""
                INSERT INTO transactions (tx_id, table_identifier, status, proposed_metadata, previous_metadata, timestamp)
                VALUES (?, ?, 'PREPARED', ?, ?, ?)
            """, (tx_id, table_id, new_metadata_path, expected_metadata_path, time.time()))
            conn.commit()
            
            log(f"[TX: {tx_id[:8]}] Phase 1 SUCCESS: Catalog lock acquired, OCC checks passed.", Colors.GREEN)

            # Simulated injected failure in Phase 1
            if fail_phase == "phase1":
                raise RuntimeError("Injected system crash during Phase 1 (Can-Commit).")

            # ========================================================
            # PHASE 2: PRE-COMMIT (Prepare State and Staging files)
            # ========================================================
            log(f"[TX: {tx_id[:8]}] Phase 2 (Pre-Commit) Started.", Colors.BLUE)
            
            # Verify if the physical proposed metadata file actually exists in sandbox
            if not os.path.exists(new_metadata_path):
                raise FileNotFoundError(f"Proposed metadata file {new_metadata_path} not written on disk.")

            # Update Transaction Status to PRECOMMITTED
            cursor.execute("UPDATE transactions SET status = 'PRECOMMITTED' WHERE tx_id = ?", (tx_id,))
            conn.commit()
            log(f"[TX: {tx_id[:8]}] Phase 2 SUCCESS: Metadata file verified on storage, transaction marked PRECOMMITTED.", Colors.GREEN)

            # Simulated injected failure in Phase 2
            if fail_phase == "phase2":
                raise RuntimeError("Injected coordinator/cohort network crash during Phase 2 (Pre-Commit).")

            # ========================================================
            # PHASE 3: DO-COMMIT (Atomic Swap & Lock Release)
            # ========================================================
            log(f"[TX: {tx_id[:8]}] Phase 3 (Do-Commit) Started.", Colors.BLUE)
            
            # Simulated injected failure in Phase 3 (Before database updates)
            if fail_phase == "phase3":
                raise RuntimeError("Injected network split during Phase 3 (Do-Commit) pointer update.")

            # Update tables catalog pointer
            cursor.execute("UPDATE tables SET metadata_location = ? WHERE table_identifier = ?", (new_metadata_path, table_id))
            
            # Update Transaction Status to COMMITTED
            cursor.execute("UPDATE transactions SET status = 'COMMITTED' WHERE tx_id = ?", (tx_id,))
            
            # Release Table Lock
            cursor.execute("DELETE FROM active_locks WHERE table_identifier = ?", (table_id,))
            conn.commit()
            log(f"[TX: {tx_id[:8]}] Phase 3 SUCCESS: Table pointer swapped to '{os.path.basename(new_metadata_path)}'. TX COMMITTED.", Colors.GREEN, bold=True)
            conn.close()
            return True

        except Exception as e:
            conn.close()
            log(f"[TX: {tx_id[:8]}] Transaction aborting. Triggering rollback. Error: {str(e)}", Colors.FAIL)
            self._execute_3pc_rollback(table_id, tx_id)
            raise e

    def _execute_3pc_rollback(self, table_id, tx_id):
        """
        Rollback coordinator sequence:
        1. Clean transaction state in catalog to ABORTED.
        2. Release active lock for table_id.
        3. Delete the orphaned metadata and manifest files created during the transaction.
        """
        log(f"[TX: {tx_id[:8]}] Rollback process initiated.", Colors.WARNING)
        conn = sqlite3.connect(CATALOG_DB)
        cursor = conn.cursor()
        try:
            # Query proposed files to delete
            cursor.execute("SELECT proposed_metadata FROM transactions WHERE tx_id = ?", (tx_id,))
            row = cursor.fetchone()
            proposed_metadata = row[0] if row else None

            # Mark TX as ABORTED
            cursor.execute("UPDATE transactions SET status = 'ABORTED' WHERE tx_id = ?", (tx_id,))
            
            # Release Lock
            cursor.execute("DELETE FROM active_locks WHERE table_identifier = ? AND locked_by_tx = ?", (table_id, tx_id))
            conn.commit()
            
            # Clean physical orphaned metadata files
            if proposed_metadata and os.path.exists(proposed_metadata):
                try:
                    # Load metadata to find manifest lists or data files written
                    with open(proposed_metadata, 'r') as f:
                        meta_data = json.load(f)
                    
                    # Delete metadata file
                    os.remove(proposed_metadata)
                    log(f"[TX: {tx_id[:8]}] Cleaned metadata file: {os.path.basename(proposed_metadata)}", Colors.CYAN)
                    
                    # Delete manifests/data files linked in current snapshot if any
                    current_snap_id = meta_data.get("current-snapshot-id")
                    for snap in meta_data.get("snapshots", []):
                        if snap.get("snapshot-id") == current_snap_id:
                            manifest_list = snap.get("manifest-list")
                            if manifest_list and os.path.exists(manifest_list):
                                # Load manifest to clean data files
                                with open(manifest_list, 'r') as mf:
                                    manifest_content = json.load(mf)
                                for data_file in manifest_content.get("data-files", []):
                                    if os.path.exists(data_file):
                                        os.remove(data_file)
                                        log(f"[TX: {tx_id[:8]}] Cleaned orphaned data file: {os.path.basename(data_file)}", Colors.CYAN)
                                os.remove(manifest_list)
                                log(f"[TX: {tx_id[:8]}] Cleaned orphaned manifest list: {os.path.basename(manifest_list)}", Colors.CYAN)
                except Exception as clean_err:
                    log(f"[TX: {tx_id[:8]}] Failed to clean orphaned files completely: {str(clean_err)}", Colors.WARNING)

            log(f"[TX: {tx_id[:8]}] Rollback complete. Consistency maintained.", Colors.GREEN)
        except Exception as rollback_db_err:
            log(f"[TX: {tx_id[:8]}] CRITICAL rollback db failure: {str(rollback_db_err)}", Colors.FAIL)
        finally:
            conn.close()

def generate_initial_metadata(table_id):
    """
    Creates structural Apache Iceberg Table Metadata v2.
    """
    metadata = {
        "format-version": 2,
        "table-uuid": str(uuid.uuid4()),
        "location": SANDBOX_DIR,
        "last-sequence-number": 0,
        "last-updated-ms": int(time.time() * 1000),
        "last-column-id": 3,
        "current-schema-id": 0,
        "schemas": [
            {
                "type": "struct",
                "schema-id": 0,
                "fields": [
                    {"id": 1, "name": "id", "required": True, "type": "int"},
                    {"id": 2, "name": "timestamp", "required": True, "type": "double"},
                    {"id": 3, "name": "payload", "required": False, "type": "string"}
                ]
            }
        ],
        "default-spec-id": 0,
        "partition-specs": [{"spec-id": 0, "fields": []}],
        "last-partition-id": 999,
        "default-sort-order-id": 0,
        "sort-orders": [{"order-id": 0, "fields": []}],
        "snapshots": [],
        "current-snapshot-id": -1,
        "snapshot-log": [],
        "metadata-log": []
    }
    return metadata

def build_new_metadata_state(current_meta, new_data_files, new_records_count):
    """
    Generates new metadata update simulating append operations in Iceberg.
    """
    new_meta = current_meta.copy()
    new_seq_num = current_meta.get("last-sequence-number", 0) + 1
    new_snapshot_id = abs(hash(str(uuid.uuid4())))
    timestamp_ms = int(time.time() * 1000)
    
    # Save the manifest list linking data files
    manifest_list_path = os.path.join(METADATA_DIR, f"snap-{new_snapshot_id}.json")
    manifest_content = {
        "manifest-id": new_snapshot_id,
        "data-files": new_data_files
    }
    with open(manifest_list_path, 'w') as f:
        json.dump(manifest_content, f, indent=2)

    new_snapshot = {
        "sequence-number": new_seq_num,
        "snapshot-id": new_snapshot_id,
        "timestamp-ms": timestamp_ms,
        "summary": {
            "operation": "append",
            "added-data-files": str(len(new_data_files)),
            "added-records": str(new_records_count)
        },
        "manifest-list": manifest_list_path
    }
    
    new_meta["last-sequence-number"] = new_seq_num
    new_meta["last-updated-ms"] = timestamp_ms
    new_meta["snapshots"] = current_meta.get("snapshots", []) + [new_snapshot]
    new_meta["current-snapshot-id"] = new_snapshot_id
    
    if current_meta.get("current-snapshot-id", -1) != -1:
        new_meta["snapshot-log"] = current_meta.get("snapshot-log", []) + [
            {"snapshot-id": current_meta["current-snapshot-id"], "timestamp-ms": current_meta["last-updated-ms"]}
        ]
        
    return new_meta

class ConcurrentWorker:
    """
    Simulates a database pipeline client writing batches to the Iceberg table.
    Implements OCC commit loop with random backoffs.
    """
    def __init__(self, worker_name, catalog, table_id, records_to_write, max_retries=5):
        self.worker_name = worker_name
        self.catalog = catalog
        self.table_id = table_id
        self.records_to_write = records_to_write
        self.max_retries = max_retries
        self.success = False
        self.attempts = 0

    def run(self):
        log(f"Worker {self.worker_name} started payload prep ({len(self.records_to_write)} records).", Colors.BLUE)
        backoff = 0.1
        
        while self.attempts < self.max_retries:
            self.attempts += 1
            tx_id = str(uuid.uuid4())
            log(f"Worker {self.worker_name}: Attempt {self.attempts}/{self.max_retries} (TX: {tx_id[:8]})", Colors.BLUE)
            
            # Step 1: Read current metadata state from catalog
            expected_metadata_path = self.catalog.get_table_metadata_pointer(self.table_id)
            if not expected_metadata_path:
                log(f"Worker {self.worker_name}: Table {self.table_id} pointer not found! Retrying...", Colors.WARNING)
                time.sleep(backoff)
                continue
                
            try:
                with open(expected_metadata_path, 'r') as f:
                    current_meta = json.load(f)
            except Exception as e:
                log(f"Worker {self.worker_name}: Failed to read metadata pointer: {str(e)}", Colors.WARNING)
                time.sleep(backoff)
                continue

            # Step 2: Write temporary data files to local storage
            data_file_id = str(uuid.uuid4())
            data_file_path = os.path.join(DATA_DIR, f"{data_file_id}.csv")
            
            try:
                with open(data_file_path, 'w') as f:
                    f.write("id,timestamp,payload\n")
                    for row in self.records_to_write:
                        f.write(f"{row[0]},{row[1]},{row[2]}\n")
            except Exception as e:
                log(f"Worker {self.worker_name}: Disk write failed: {str(e)}", Colors.FAIL)
                time.sleep(backoff)
                continue

            # Step 3: Build proposed metadata file locally
            proposed_meta = build_new_metadata_state(current_meta, [data_file_path], len(self.records_to_write))
            new_metadata_path = os.path.join(METADATA_DIR, f"v-{tx_id}.metadata.json")
            
            try:
                with open(new_metadata_path, 'w') as f:
                    json.dump(proposed_meta, f, indent=2)
            except Exception as e:
                log(f"Worker {self.worker_name}: Metadata write failed: {str(e)}", Colors.FAIL)
                os.remove(data_file_path)
                time.sleep(backoff)
                continue

            # Step 4: Attempt 3PC commit to catalog
            try:
                # Add small jitter to exacerbate collisions in SQLite
                time.sleep(random.uniform(0.01, 0.05))
                
                self.catalog.execute_3pc_commit(
                    table_id=self.table_id,
                    tx_id=tx_id,
                    expected_metadata_path=expected_metadata_path,
                    new_metadata_path=new_metadata_path
                )
                self.success = True
                log(f"Worker {self.worker_name} COMMITTED successfully on attempt {self.attempts}!", Colors.GREEN, bold=True)
                break
            except Exception as commit_error:
                log(f"Worker {self.worker_name} Commit FAILED (Attempt {self.attempts}): {str(commit_error)}", Colors.WARNING)
                # Exponential backoff + jitter
                sleep_time = backoff * (2 ** (self.attempts - 1)) + random.uniform(0.01, 0.1)
                log(f"Worker {self.worker_name} backing off for {sleep_time:.3f}s...", Colors.BLUE)
                time.sleep(sleep_time)
                
        if not self.success:
            log(f"Worker {self.worker_name} failed all {self.max_retries} commit attempts.", Colors.FAIL, bold=True)


def run_scenario_single_commit(catalog, table_id):
    """
    Scenario 1: Standard single write commit to setup metadata architecture
    """
    log("==================================================================", Colors.HEADER, bold=True)
    log("SCENARIO 1: Initialization and First Commit Flow", Colors.HEADER, bold=True)
    log("==================================================================", Colors.HEADER, bold=True)
    
    # Init initial metadata file
    tx_id = str(uuid.uuid4())
    initial_meta = generate_initial_metadata(table_id)
    initial_meta_path = os.path.join(METADATA_DIR, "v0.metadata.json")
    with open(initial_meta_path, 'w') as f:
        json.dump(initial_meta, f, indent=2)
        
    catalog.initialize_table(table_id, initial_meta_path)
    log(f"Table '{table_id}' registered in Catalog with metadata pointer: {os.path.basename(initial_meta_path)}", Colors.CYAN)

    # First write
    records = [(100, time.time(), "Initial pipeline ingest record")]
    worker = ConcurrentWorker("Bootstrapper", catalog, table_id, records)
    worker.run()
    
    new_ptr = catalog.get_table_metadata_pointer(table_id)
    log(f"Scenario 1 Complete. Catalog current metadata pointer: {os.path.basename(new_ptr)}", Colors.GREEN, bold=True)


def run_scenario_occ_collisions(catalog, table_id):
    """
    Scenario 2: Fire concurrent threads to simulate write collisions and show OCC resolution.
    """
    log("\n==================================================================", Colors.HEADER, bold=True)
    log("SCENARIO 2: Concurrent Writers & OCC Collision Control", Colors.HEADER, bold=True)
    log("==================================================================", Colors.HEADER, bold=True)

    workers = []
    # Create 4 concurrent workers attempting to write rows at the exact same time
    for i in range(1, 5):
        records = [
            (i * 10 + j, time.time(), f"Record from concurrent writer #{i} - seq {j}")
            for j in range(3)
        ]
        # Allow enough retries to resolve the collisions
        workers.append(ConcurrentWorker(f"Writer-{i}", catalog, table_id, records, max_retries=8))

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(w.run): w for w in workers}
        for future in as_completed(futures):
            future.result()

    successful_workers = sum(1 for w in workers if w.success)
    log(f"\nOCC Concurrency Simulation Done. Successful workers: {successful_workers}/4", Colors.GREEN, bold=True)
    for w in workers:
        status_color = Colors.GREEN if w.success else Colors.FAIL
        log(f" -> {w.worker_name}: {'COMPLETED' if w.success else 'FAILED'} in {w.attempts} attempts", status_color)


def run_scenario_fault_injection(catalog, table_id):
    """
    Scenario 3: Simulates system and network failures at specific phases of the 3PC sequence
    to prove transactional robustness.
    """
    log("\n==================================================================", Colors.HEADER, bold=True)
    log("SCENARIO 3: 3PC Phase Failures and State Rollback", Colors.HEADER, bold=True)
    log("==================================================================", Colors.HEADER, bold=True)

    # Prepare transaction metadata
    expected_ptr = catalog.get_table_metadata_pointer(table_id)
    with open(expected_ptr, 'r') as f:
        current_meta = json.load(f)

    # Write mock data file
    data_file_path = os.path.join(DATA_DIR, "fault_inject_data.csv")
    with open(data_file_path, 'w') as f:
        f.write("id,timestamp,payload\n9999,0.0,Fault Injection Row\n")

    # Build metadata path
    tx_id_phase2 = str(uuid.uuid4())
    proposed_meta = build_new_metadata_state(current_meta, [data_file_path], 1)
    new_metadata_path = os.path.join(METADATA_DIR, f"v-{tx_id_phase2}.metadata.json")
    with open(new_metadata_path, 'w') as f:
        json.dump(proposed_meta, f, indent=2)

    log("Injecting Coordinator Failure inside Phase 2 (Pre-Commit)...", Colors.WARNING, bold=True)
    try:
        catalog.execute_3pc_commit(
            table_id=table_id,
            tx_id=tx_id_phase2,
            expected_metadata_path=expected_ptr,
            new_metadata_path=new_metadata_path,
            fail_phase="phase2" # Inject crash right after status is marked as PRECOMMITTED
        )
    except Exception as err:
        log(f"Intercepted failure exception as expected: {str(err)}", Colors.CYAN)

    # Verification: Validate that the lock was released and proposed metadata file was garbage collected
    current_ptr = catalog.get_table_metadata_pointer(table_id)
    log(f"Verify Catalog Pointer remains consistent: {os.path.basename(current_ptr)}", Colors.GREEN)
    
    db_file_check = os.path.exists(new_metadata_path)
    log(f"Verify proposed metadata file deleted: {not db_file_check} (File exists: {db_file_check})", Colors.GREEN)
    
    data_file_check = os.path.exists(data_file_path)
    log(f"Verify orphaned data file deleted: {not data_file_check} (File exists: {data_file_check})", Colors.GREEN)


def query_and_verify_table(catalog, table_id):
    """
    Scenario 4: Analytical Verification. Uses DuckDB (or SQLite fallback) to read metadata log
    and scan all data files registered in active snapshots.
    """
    log("\n==================================================================", Colors.HEADER, bold=True)
    log("SCENARIO 4: Data Engine Analytics Verification", Colors.HEADER, bold=True)
    log("==================================================================", Colors.HEADER, bold=True)

    current_ptr = catalog.get_table_metadata_pointer(table_id)
    if not current_ptr:
        log("No metadata pointer found in catalog. Verify script failure.", Colors.FAIL)
        return

    with open(current_ptr, 'r') as f:
        metadata = json.load(f)

    log(f"Loading Metadata: {os.path.basename(current_ptr)}", Colors.CYAN)
    log(f"Active Snapshots: {len(metadata.get('snapshots', []))}", Colors.CYAN)
    log(f"Current Schema Fields: {json.dumps(metadata['schemas'][0]['fields'])}", Colors.CYAN)

    # Gather all active data files referenced in snapshots
    data_files = []
    for snapshot in metadata.get("snapshots", []):
        manifest_list_path = snapshot.get("manifest-list")
        if manifest_list_path and os.path.exists(manifest_list_path):
            with open(manifest_list_path, 'r') as mf:
                manifest = json.load(mf)
                for df in manifest.get("data-files", []):
                    if os.path.exists(df):
                        data_files.append(df)

    log(f"Discovered {len(data_files)} active committed CSV data partitions.", Colors.CYAN)
    
    if not data_files:
        log("No data files available for queries.", Colors.WARNING)
        return

    # Check if DuckDB is installed in environment
    has_duckdb = False
    try:
        import duckdb
        has_duckdb = True
    except ImportError:
        log("DuckDB not installed in environment. Falling back to SQLite for data validation.", Colors.WARNING)

    if has_duckdb:
        log("Executing Analytics query using DuckDB Engine...", Colors.BLUE)
        con = duckdb.connect(database=':memory:')
        
        # Load CSV files into duckdb
        file_list_str = ", ".join([f"'{df}'" for df in data_files])
        try:
            con.execute(f"CREATE TABLE data_view AS SELECT * FROM read_csv_auto([{file_list_str}])")
            
            # Query sum/count metrics
            result_total = con.execute("SELECT COUNT(*), SUM(id) FROM data_view").fetchone()
            log(f"DuckDB Query Success: Count = {result_total[0]} rows, Sum(id) = {result_total[1]}", Colors.GREEN, bold=True)
            
            log("Detailed Table Sample (DuckDB):", Colors.CYAN)
            samples = con.execute("SELECT id, timestamp, payload FROM data_view ORDER BY id LIMIT 5").fetchall()
            for row in samples:
                log(f"  ID: {row[0]} | Time: {row[1]:.4f} | Msg: {row[2]}", Colors.CYAN)
        except Exception as q_err:
            log(f"DuckDB Query Execution Error: {str(q_err)}", Colors.FAIL)
    else:
        # SQLite analytical fallback
        log("Executing Analytics query using SQLite Engine...", Colors.BLUE)
        db_conn = sqlite3.connect(":memory:")
        db_cursor = db_conn.cursor()
        db_cursor.execute("CREATE TABLE data_view (id INT, timestamp REAL, payload TEXT)")
        
        for df in data_files:
            with open(df, 'r') as f:
                lines = f.readlines()
                for line in lines[1:]: # skip headers
                    parts = line.strip().split(',')
                    if len(parts) >= 3:
                        db_cursor.execute("INSERT INTO data_view VALUES (?, ?, ?)", (int(parts[0]), float(parts[1]), parts[2]))
        db_conn.commit()

        result_total = db_cursor.execute("SELECT COUNT(*), SUM(id) FROM data_view").fetchone()
        log(f"SQLite Query Success: Count = {result_total[0]} rows, Sum(id) = {result_total[1]}", Colors.GREEN, bold=True)
        
        log("Detailed Table Sample (SQLite):", Colors.CYAN)
        samples = db_cursor.execute("SELECT id, timestamp, payload FROM data_view ORDER BY id LIMIT 5").fetchall()
        for row in samples:
            log(f"  ID: {row[0]} | Time: {row[1]:.4f} | Msg: {row[2]}", Colors.CYAN)
        db_conn.close()


def clean_sandbox_directories():
    """
    Cleans up execution sandbox folders
    """
    if os.path.exists(SANDBOX_DIR):
        shutil.rmtree(SANDBOX_DIR)
    os.makedirs(SANDBOX_DIR)
    os.makedirs(DATA_DIR)
    os.makedirs(METADATA_DIR)


def main():
    table_id = "default.snowflake_sovereign_table"
    
    clean_sandbox_directories()
    
    catalog = IcebergCatalog()
    
    # Run Scenario 1: Setup and single commit
    run_scenario_single_commit(catalog, table_id)
    
    # Run Scenario 2: OCC Write Collisions
    run_scenario_occ_collisions(catalog, table_id)
    
    # Run Scenario 3: 3PC Commit failures with rollback
    run_scenario_fault_injection(catalog, table_id)
    
    # Run Scenario 4: Analytical checks
    query_and_verify_table(catalog, table_id)


if __name__ == "__main__":
    main()
