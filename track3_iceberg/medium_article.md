# Taming the Thundering Herd: 3-Phase Commits and Swarm Synchronization in Apache Iceberg

The modern data lakehouse architecture promises the best of both worlds: the cost-effective scalability of object storage and the rigorous ACID transaction guarantees of traditional relational database systems. At the center of this paradigm is Apache Iceberg, an open-source high-performance table format designed for massive analytic datasets. Iceberg manages state changes by writing immutable metadata files, tracking table schemas, partition specifications, and snapshot histories. 

To govern concurrent writes without incurring the overhead of heavy distributed locking mechanisms, Iceberg employs **Optimistic Concurrency Control (OCC)**. Under low-to-moderate concurrency, OCC performs exceptionally well. However, when scale demands that dozens of autonomous data pipelines, microservices, and ingestion agents write to the same table concurrently, OCC breaks down. 

Uncoordinated agents begin to clash over the catalog pointer, causing transaction failures, redundant I/O, and an architectural pathology known as a **retry storm**.

In this article, we will examine the engineering physics behind OCC retry storms by linking them to the **Kuramoto Oscillator Model** of distributed swarm synchronization. We will then construct a mathematical model for mitigating these storms using randomized jitter, and walk through how to build a resilient **3-Phase Commit (3PC)** transaction protocol with deterministic rollback logic to ensure catalog-to-storage integrity.

---

## 1. The Physics of the Bottleneck: Kuramoto Oscillators & OCC Retry Storms

To understand why concurrent writes fail under load, we must first map the lifecycle of an Iceberg commit. When an ingestion client (such as a Spark or Flink pipeline) writes to a table:
1. **Read**: The client queries the catalog to locate the current table metadata pointer ($V_n$, referencing Snapshot $S_n$).
2. **Write**: The client writes new data files (e.g., Parquet) to object storage and compiles a new proposed metadata file ($V_{n+1}$).
3. **Commit**: The client attempts to update the catalog's pointer from $V_n$ to $V_{n+1}$. The catalog validates that the current active pointer is still $V_n$. If it has changed, a write collision occurs, the transaction is aborted, the proposed files are discarded, and the client retries the entire process.

```
       Timeline of Ingestion Commits
       
Worker 1: [--- Read V0 ---][--- Write Data ---][=== Commit V1 (Success) ===]
Worker 2:    [--- Read V0 ---][--- Write Data ---][=== Commit V2 (Collision Abort -> Retry) ===]
Worker 3:       [--- Read V0 ---][--- Write Data ---][=== Commit V2 (Collision Abort -> Retry) ===]
```

When many concurrent workers attempt this cycle, a positive feedback loop develops. This is a classic example of **collective synchronization**, a phenomenon modeled in physics by the **Kuramoto Oscillator Model**. 

### The Kuramoto Model in Distributed Systems
The Kuramoto model describes the phase dynamics of a population of $N$ coupled limit-cycle oscillators. The phase $\theta_i$ of the $i$-th oscillator evolves over time according to:

$$\frac{d\theta_i}{dt} = \omega_i + \frac{K}{N} \sum_{j=1}^{N} \sin(\theta_j - \theta_i)$$

Where $\omega_i$ is the natural frequency of the oscillator, $K$ is the coupling strength, and $N$ is the total number of oscillators. 

In a distributed database pipeline, we can model each ingestion worker as an oscillator. The "phase" $\theta_i$ represents the worker's progress through its read-write-commit loop, and the natural frequency $\omega_i$ is determined by the speed of its ingestion data processing. 

The coupling factor $K$ represents the catalog's atomic pointer check. When a worker successfully commits, it changes the pointer. This instantly resets the phase of all other active workers back to $\theta = 0$ (the start of the retry loop).

Without coordination, these independent workers will **phase-lock**. They align their retry cycles and execute their loops in lockstep. This is the **Thundering Herd** effect:

1. **System Reset**: A successful commit by one worker aborts the transactions of all other concurrent workers.
2. **Synchronized Backoff**: The aborted workers wait for their scheduled backoff interval. Because their base intervals are identical, they sleep for the same duration.
3. **Coincident Commits**: The workers wake up and attempt to commit at the exact same instant, causing a 100% collision rate.

As concurrency increases, the effective coupling strength $K$ grows. The system phase-locks into a state where write throughput drops to zero, while the database is flooded with redundant I/O requests.

---

## 2. Breaking the Symmetry: The Mathematical Model of Jitter

To break this collective synchronization, we must disrupt the coupling term in the Kuramoto equations. We achieve this by introducing randomized temporal asymmetry—specifically, **randomized jitter** in the retry backoff calculation.

The backoff latency $T_{\text{backoff}}$ for the $k$-th retry attempt is defined by:

$$T_{\text{backoff}}(k) = \min\left(T_{\text{max}}, T_{\text{base}} \cdot 2^{k-1} + U(0, J)\right)$$

Where:
* $T_{\text{base}}$ is the initial base backoff interval (e.g., 100 milliseconds).
* $T_{\text{max}}$ is the maximum cap on the backoff time (e.g., 5 seconds).
* $k \in \{1, 2, \dots, N_{\text{max}}\}$ is the current retry index.
* $U(0, J)$ is a uniform random variable representing the randomized jitter between $0$ and $J$.

By adding $U(0, J)$, we introduce a stochastic phase shift. The oscillators are no longer coupled to a single master phase. This randomized delay shifts the commit attempts away from a single point in time, distributing them uniformly across the temporal dimension:

```
               Distribution of Commit Attempts over Time
               
Without Jitter (Phase-Locked):
||||                                ||||                                ||||
+-----------------------------------+-----------------------------------+------------> Time
(Synchronized Thundering Herd)

With Jitter (Asymmetric):
  |    |  |     |   |    |    |  |    |  |     |   |    |    |  |   |    |   |    |  |
+------------------------------------------------------------------------------------> Time
(Asynchronous distributed commits)
```

---

## 3. Ensuring Atomicity: The 3-Phase Commit (3PC) Protocol

Solving the retry storm at the client level is only half the battle. In modern enterprise architectures, the catalog metadata store (typically a relational DB like RDS PostgreSQL or a REST Catalog instance) is separated from the physical storage layer (like AWS S3). 

If a coordinator crashes or encounters a network partition during a standard 2-Phase Commit (2PC) sequence, the database can enter an inconsistent state. The catalog pointer may point to a file that does not exist on storage, or storage may fill up with orphaned data blocks that are never garbage-collected.

To solve this, we can implement a **3-Phase Commit (3PC)** protocol. 3PC is a non-blocking protocol that splits the commit path into three distinct phases:

1. **Can-Commit?**: The coordinator checks if the table row lock is available and runs the OCC check. If the expected metadata pointer matches the active pointer, it reserves a transaction lock.
2. **Pre-Commit**: The coordinator writes the transaction record to the catalog database with a status of `PRECOMMITTED` and verifies that the client has successfully uploaded the new metadata and data files to storage.
3. **Do-Commit**: The coordinator updates the catalog's active metadata pointer, changes the transaction status to `COMMITTED`, and releases the lock.

If a failure occurs during Phase 1 or Phase 2, the coordinator aborts the transaction and rolls back the system state.

---

## 4. Code Breakdown: The 3PC Commit and Rollback Engine

Let's examine how this protocol is implemented in Python. The following code snippet from our [validation engine](file:///home/abhishek/ObsidianVault/03_Active_Projects/snowflake_sovereign_portfolio/track3_iceberg/validate_engine.py) shows the coordinator commit sequence and the rollback handler:

```python
    def execute_3pc_commit(self, table_id, tx_id, expected_metadata_path, new_metadata_path, fail_phase=None):
        """
        Coordinates a 3-Phase Commit (3PC):
        1. Phase 1: Can-Commit? (OCC Check + Table Lock)
        2. Phase 2: Pre-Commit (Verify physical metadata exists and log status)
        3. Phase 3: Do-Commit (Update Catalog Pointer to new state)
        """
        conn = sqlite3.connect(CATALOG_DB)
        cursor = conn.cursor()

        try:
            # ========================================================
            # PHASE 1: CAN-COMMIT?
            # ========================================================
            # Verify Table Row Lock
            cursor.execute("SELECT locked_by_tx FROM active_locks WHERE table_identifier = ?", (table_id,))
            lock_row = cursor.fetchone()
            if lock_row:
                active_tx = lock_row[0]
                raise sqlite3.OperationalError(f"Table locked by active TX {active_tx[:8]}.")

            # OCC Validation: Check if table metadata pointer has changed since worker started
            cursor.execute("SELECT metadata_location FROM tables WHERE table_identifier = ?", (table_id,))
            current_row = cursor.fetchone()
            current_metadata = current_row[0] if current_row else None
            
            if current_metadata != expected_metadata_path:
                raise ValueError("OCC Write Collision detected. Transaction aborted.")

            # Lock the table row for the 3PC sequence
            cursor.execute("INSERT INTO active_locks (table_identifier, locked_by_tx, lock_time) VALUES (?, ?, ?)",
                           (table_id, tx_id, time.time()))
            
            # Record TX status as PREPARED
            cursor.execute("""
                INSERT INTO transactions (tx_id, table_identifier, status, proposed_metadata, previous_metadata, timestamp)
                VALUES (?, ?, 'PREPARED', ?, ?, ?)
            """, (tx_id, table_id, new_metadata_path, expected_metadata_path, time.time()))
            conn.commit()

            # ========================================================
            # PHASE 2: PRE-COMMIT
            # ========================================================
            # Verify if the physical proposed metadata file exists on storage
            if not os.path.exists(new_metadata_path):
                raise FileNotFoundError(f"Proposed metadata file {new_metadata_path} not written on disk.")

            # Update Transaction Status to PRECOMMITTED
            cursor.execute("UPDATE transactions SET status = 'PRECOMMITTED' WHERE tx_id = ?", (tx_id,))
            conn.commit()

            # Simulated injected failure in Phase 2
            if fail_phase == "phase2":
                raise RuntimeError("Injected system crash during Phase 2 (Pre-Commit).")

            # ========================================================
            # PHASE 3: DO-COMMIT
            # ========================================================
            # Update tables catalog pointer
            cursor.execute("UPDATE tables SET metadata_location = ? WHERE table_identifier = ?", (new_metadata_path, table_id))
            
            # Update Transaction Status to COMMITTED
            cursor.execute("UPDATE transactions SET status = 'COMMITTED' WHERE tx_id = ?", (tx_id,))
            
            # Release Table Lock
            cursor.execute("DELETE FROM active_locks WHERE table_identifier = ?", (table_id,))
            conn.commit()
            conn.close()
            return True

        except Exception as e:
            conn.close()
            # If any failure occurs, trigger rollback
            self._execute_3pc_rollback(table_id, tx_id)
            raise e
```

### Breaking Down the Rollback Logic
If any of the assertions in the commit block fail (such as a lock collision or a file-not-found error on storage), the coordinator catches the exception and routes the transaction to the rollback function:

```python
    def _execute_3pc_rollback(self, table_id, tx_id):
        """
        Rollback coordinator sequence:
        1. Set transaction state in catalog to ABORTED.
        2. Release the lock for table_id.
        3. Delete the orphaned metadata and manifest files created during the transaction.
        """
        conn = sqlite3.connect(CATALOG_DB)
        cursor = conn.cursor()
        try:
            # Query proposed files to delete
            cursor.execute("SELECT proposed_metadata FROM transactions WHERE tx_id = ?", (tx_id,))
            row = cursor.fetchone()
            proposed_metadata = row[0] if row else None

            # Mark TX as ABORTED and release lock
            cursor.execute("UPDATE transactions SET status = 'ABORTED' WHERE tx_id = ?", (tx_id,))
            cursor.execute("DELETE FROM active_locks WHERE table_identifier = ? AND locked_by_tx = ?", (table_id, tx_id))
            conn.commit()
            
            # Clean physical orphaned metadata files
            if proposed_metadata and os.path.exists(proposed_metadata):
                with open(proposed_metadata, 'r') as f:
                    meta_data = json.load(f)
                
                # Delete metadata file
                os.remove(proposed_metadata)
                
                # Delete manifests/data files linked in the current proposed snapshot
                current_snap_id = meta_data.get("current-snapshot-id")
                for snap in meta_data.get("snapshots", []):
                    if snap.get("snapshot-id") == current_snap_id:
                        manifest_list = snap.get("manifest-list")
                        if manifest_list and os.path.exists(manifest_list):
                            with open(manifest_list, 'r') as mf:
                                manifest_content = json.load(mf)
                            for data_file in manifest_content.get("data-files", []):
                                if os.path.exists(data_file):
                                    os.remove(data_file)
                            os.remove(manifest_list)
        except Exception as rollback_err:
            # Log critical database error for administrators
            pass
        finally:
            conn.close()
```

### Rollback Process Analysis
The rollback logic follows a strict order to ensure consistency:
1. **Catalog First**: It immediately updates the catalog database status of `tx_id` to `ABORTED` and releases the lock. This allows waiting client pipelines to proceed without delay.
2. **Metadata Traversal**: It parses the orphaned proposed metadata file to extract the location of the manifest list created during the transaction.
3. **Data File Erasure**: It reads the manifest list file to identify the precise physical data file paths written during the ingestion step. It deletes these files to free up storage space.
4. **Storage Cleanup**: Finally, it deletes the manifest list and metadata files, removing all traces of the failed transaction.

---

## 5. Architectural Trade-offs

When designing write control mechanisms for metadata catalogs, engineers must balance consistency, latency, and system complexity. The table below outlines the trade-offs of the primary options:

| Metric | 2-Phase Commit (2PC) | 3-Phase Commit (3PC) | Single-Catalog Locks (Pessimistic) |
| :--- | :--- | :--- | :--- |
| **Commit Latency** | Low (2 Round-Trips) | Moderate (3 Round-Trips) | High (Pipelines wait in queue) |
| **Coordinator Crash Resiliency** | **Vulnerable**: Cohorts block indefinitely if the coordinator crashes mid-commit. | **Resilient**: Cohorts resolve transaction status independently using log state. | **Vulnerable**: Orphaned locks require manual administrator overrides. |
| **Orphaned File Garbage** | High | Low (Immediate cleanup on rollback) | None (No data is written if the lock is held) |
| **System Complexity** | Medium | High | Low |

For most analytical databases, OCC with exponential backoff and randomized jitter is the ideal choice for client-side write control. If you have decoupled catalog and storage systems, introducing a 3-Phase Commit protocol ensures that the data lake remains consistent, even in the event of hardware or network failures.

By understanding the dynamics of swarm synchronization and implementing structured transaction protocols, we can build robust, high-throughput systems that scale to meet the demands of modern data ingestion workloads.
