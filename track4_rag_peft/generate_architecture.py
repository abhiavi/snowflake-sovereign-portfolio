#!/usr/bin/env python3
"""
generate_architecture.py
================================================================================
Generates the architecture diagram for the Sovereign AI RAG & PEFT Pipeline
using the Python `diagrams` library.

Mandated Layout:
- graph_attr: layout="dot", compound="true", splines="spline", nodesep="1.0", ranksep="1.5"
- Flow: Unstructured Data -> Semantic Chunker -> PII Redaction Engine (DPDP Compliant) -> Vector Embedding -> LiteLLM Context Window
================================================================================
"""

import sys
from diagrams import Diagram, Cluster, Edge
from diagrams.generic.blank import Blank
from diagrams.generic.database import SQL
from diagrams.generic.device import Tablet
from diagrams.onprem.compute import Server
from diagrams.onprem.security import Vault

node_attr = {
    "fontname": "Helvetica",
    "fontsize": "18",       # Bumping this from 12/13 to 18 makes the text larger relative to the icon
    "fontcolor": "black",   # Overrides Track 4's white text
    "shape": "box",
    "style": "rounded,filled",
    "fillcolor": "white",
    "color": "black"
}

node_attr = {
    "fontcolor": "#ffffff",
    "fontsize": "12",
    "fontname": "Sans-Serif",
    "style": "filled",
    "fillcolor": "#2d2d2d",
    "color": "#4f4f4f"
}

edge_attr = {
    "color": "#00ffcc",
    "style": "solid",
    "penwidth": "2.0"
}

def generate_diagram():
    print("Generating architecture diagram via 'diagrams' library...")
    
    with Diagram(
        "Sovereign RAG & PEFT Pipeline Ingestion",
        show=False,
        filename="sovereign_architecture",
        outformat="png",
        graph_attr=graph_attr,
        edge_attr=edge_attr
    ) as diag:
        
        # Data Source node representing raw ingested files
        data_source = Tablet("Unstructured Data (Enterprise Docs)", **node_attr)
        
        # Sub-cluster for sovereign processing
        with Cluster("Sovereign Compute Boundaries (Local Host)", graph_attr={"bgcolor": "#252525", "fontcolor": "#00ffcc", "pencolor": "#4f4f4f"}):
            chunker = Server("Semantic Chunker (Cosine-Windowed)", **node_attr)
            redactor = Vault("PII Redaction Engine (DPDP Compliant)", **node_attr)
            embedder = SQL("Vector Embedding Store", **node_attr)
            
        # Context Endpoint
        litellm = Server("LiteLLM Context Window (Bypassing 6k Limit)", **node_attr)
        
        # Data Pipeline Relationships
        data_source >> Edge(label="Raw Stream", color="#ff7700", fontcolor="#ffffff") >> chunker
        chunker >> Edge(label="Segmented Chunks", color="#00ffcc", fontcolor="#ffffff") >> redactor
        redactor >> Edge(label="Sanitized Data", color="#00ffcc", fontcolor="#ffffff") >> embedder
        embedder >> Edge(label="Optimized Vectors", color="#ff007f", fontcolor="#ffffff") >> litellm

    print("Successfully generated: sovereign_architecture.png")

if __name__ == "__main__":
    generate_diagram()
