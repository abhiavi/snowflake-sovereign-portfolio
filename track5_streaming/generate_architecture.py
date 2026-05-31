#!/usr/bin/env python3
"""
generate_architecture.py
Generates the architecture diagram for Track 5 Low-Latency Streaming & ECO Egress Routing
using the Python diagrams library.
"""

from diagrams import Diagram, Edge, Cluster
from diagrams.onprem.client import Client
from diagrams.onprem.compute import Server
from diagrams.onprem.inmemory import Redis
from diagrams.aws.storage import S3
from diagrams.gcp.storage import GCS
from diagrams.azure.storage import BlobStorage
from diagrams.saas.analytics import Snowflake

# Force specific dot layout attributes as mandated
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

def generate_diagram():
    with Diagram(
        "Low-Latency Streaming & ECO Egress Caching Architecture",
        show=False,
        filename="architecture",
        outformat="png",
        graph_attr=graph_attr
    ):
        # Telemetry Source
        telemetry = Client("Telemetry Source\n(Clickstream JSON)")

        # Ingestion & Compression & Caching Pipeline
        with Cluster("Sovereign Ingestion & Caching Layer"):
            zstd_layer = Server("ZSTD Compression\nLayer (Fast Level 3)")
            eco_cache = Redis("ECO Router Cache\n(LRU OrderedDict)")
            
            # Connection within cluster
            zstd_layer >> Edge(label="Size-Prefixed TCP Stream", color="darkblue") >> eco_cache

        # Connect source to ingestion pipeline
        telemetry >> Edge(label="Uncompressed Stream", color="orange") >> zstd_layer

        # Multi-Cloud Egress Targets
        with Cluster("Multi-Cloud Target Destinations"):
            aws = S3("AWS S3\n(Egress: $0.09/GB)")
            gcp = GCS("GCP GCS\n(Egress: $0.12/GB)")
            azure = BlobStorage("Azure Blob\n(Egress: $0.087/GB)")
            snowflake = Snowflake("Snowflake\n(Egress: $0.09/GB)")
            targets = [aws, gcp, azure, snowflake]

        # Connect ECO cache to targets
        for target in targets:
            eco_cache >> Edge(label="Cache Miss (Egress Cost)", color="red", style="dashed") >> target

if __name__ == "__main__":
    generate_diagram()
    print("[+] Architecture diagram successfully generated: architecture.png")
