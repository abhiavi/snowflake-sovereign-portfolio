#!/usr/bin/env python3
import os
import sys

def main():
    try:
        from diagrams import Diagram, Cluster, Edge
        from diagrams.onprem.client import Client
        from diagrams.onprem.database import Duckdb
        from diagrams.onprem.security import Vault
        from diagrams.aws.storage import SimpleStorageServiceS3
    except ImportError:
        print("Error: The 'diagrams' library is required to run this script.")
        print("Please install it using: pip install diagrams")
        sys.exit(1)

    graph_attr = {
    "layout": "dot",
    "compound": "true",
    "splines": "ortho",    # Forces sharp right angles instead of curvy lines
    "nodesep": "1.2",      # Increases horizontal spacing
    "ranksep": "1.5",      # Increases vertical spacing
    "bgcolor": "white",    # OVERRIDES TRANSPARENCY - Fixes the black background issue
    "fontname": "Helvetica",
    "fontsize": "20"
}

    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "iceberg_architecture")

    with Diagram("Apache Iceberg Concurrency & 3PC Catalog Architecture", 
                 show=False, 
                 filename=output_path, 
                 outformat="png", 
                 graph_attr=graph_attr):
        
        with Cluster("Client Ingest Layer (Concurrent Swarms)"):
            pipelines = [
                Client("Client Pipeline A\n(Spark Streaming)"),
                Client("Client Pipeline B\n(Flink Micro-batch)"),
                Client("Client Pipeline C\n(Kafka Connect)")
            ]
        
        catalog = Duckdb("REST Catalog\n(SQLite/DuckDB Simulated)")
        occ_gate = Vault("OCC Gate\n(Optimistic Locking)")
        s3 = SimpleStorageServiceS3("S3 Data Storage\n(Parquet & Metadata Files)")
        
        # Connect pipelines to catalog
        for i, pipe in enumerate(pipelines):
            pipe >> Edge(color="blue", style="dashed", label=f"1. Begin Ingestion") >> catalog
            
        # Connect catalog to OCC gate
        catalog >> Edge(color="red", style="bold", label="2. OCC Check & Lock") >> occ_gate
        
        # Connect OCC gate to S3
        occ_gate >> Edge(color="green", style="solid", label="3. Commit Swap / Write Files") >> s3

    print(f"Architecture diagram generated successfully at: {output_path}.png")

if __name__ == "__main__":
    main()
