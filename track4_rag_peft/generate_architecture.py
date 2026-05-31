#!/usr/bin/env python3
import sys
from diagrams import Diagram, Cluster, Edge
from diagrams.aws.general import Client
from diagrams.aws.compute import EC2
from diagrams.aws.security import Macie
from diagrams.aws.database import RDS
from diagrams.aws.ml import Sagemaker

graph_attr = {
    "layout": "dot",
    "compound": "true",
    "splines": "ortho",
    "nodesep": "1.2",
    "ranksep": "1.5",
    "bgcolor": "white",
    "fontname": "Helvetica",
    "fontsize": "20"
}

node_attr = {
    "fontname": "Helvetica",
    "fontsize": "16",
    "fontcolor": "black",
    "shape": "box",
    "style": "rounded,filled",
    "fillcolor": "white",
    "color": "black"
}

edge_attr = {
    "color": "#00ffcc",
    "style": "solid",
    "penwidth": "2.0",
    "fontcolor": "black",
    "fontname": "Helvetica",
    "fontsize": "12"
}

def generate_diagram():
    print("Generating colored architecture diagram...")
    with Diagram(
        "Sovereign RAG & PEFT Pipeline Ingestion",
        show=False,
        filename="sovereign_architecture",
        outformat="png",
        graph_attr=graph_attr,
        node_attr=node_attr,
        edge_attr=edge_attr
    ):
        data_source = Client("Unstructured Data\n(Enterprise Docs)")

        with Cluster("Sovereign Compute Boundaries (Local Host)"):
            chunker = EC2("Semantic Chunker\n(Cosine-Windowed)")
            redactor = Macie("PII Redaction Engine\n(DPDP Compliant)")
            embedder = RDS("Vector Embedding Store")

        litellm = Sagemaker("LiteLLM Context Window\n(Bypassing 6k Limit)")

        data_source >> Edge(label="Raw Stream", color="#ff7700") >> chunker
        chunker >> Edge(label="Segmented Chunks", color="#000000") >> redactor
        redactor >> Edge(label="Sanitized Data", color="#000000") >> embedder
        embedder >> Edge(label="Optimized Vectors", color="#ff007f") >> litellm

if __name__ == "__main__":
    generate_diagram()
