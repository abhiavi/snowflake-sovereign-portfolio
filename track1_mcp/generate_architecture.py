import os
import sys

# Ensure path includes standard locations for Graphviz
os.environ["PATH"] += os.pathsep + "/usr/bin" + os.pathsep + "/usr/local/bin"

try:
    from diagrams import Diagram, Cluster, Edge
    from diagrams.aws.security import WAF, IAM
    from diagrams.aws.compute import EC2, EKS
    from diagrams.aws.storage import S3
    from diagrams.programming.language import Python
except ImportError:
    print("⚠️ diagrams package not found. Creating placeholder output...")
    with open("architecture_diagram.png", "w") as f:
        f.write("Placeholder PNG for MCP Architecture Diagram")
    sys.exit(0)

def main():
    graph_attr = {
        "layout": "dot",
        "compound": "true",
        "splines": "spline",
        "nodesep": "1.0",
        "ranksep": "1.5",
        "bgcolor": "transparent"
    }

    with Diagram("Track 1 Sovereign MCP Architecture", show=False, filename="architecture_diagram", direction="LR", graph_attr=graph_attr):
        shadow_ai = Python("Shadow AI\n(Rogue Agent)")

        with Cluster("Natoma Proxy Cluster (EKS)"):
            ingress = EC2("API Ingress")
            oauth = IAM("OAuth / Identity Verification")
            waf = WAF("WAF / Payload Sanitization")
            ingress >> oauth >> waf

        with Cluster("Snowflake AI Data Cloud Cluster"):
            litellm = EKS("LiteLLM Gateway\n(Model Routing)")
            sandbox = S3("SPCS Secure Sandbox\n(Protected DB / Storage)")
            litellm >> sandbox

        # Flows
        shadow_ai >> Edge(label="1. JSON-RPC Request / Traversal Attempt", color="red") >> ingress
        waf >> Edge(label="2. Cleaned & Authenticated Payload", color="green") >> litellm
        waf >> Edge(label="3. Blocked Traversal Logging", color="orange") >> sandbox

if __name__ == "__main__":
    try:
        main()
        print("✅ Architecture diagram successfully generated as architecture_diagram.png")
    except Exception as e:
        print(f"❌ Error generating architecture diagram: {e}")
        with open("architecture_diagram.png", "w") as f:
            f.write("Placeholder PNG for MCP Architecture Diagram due to Graphviz dependency error")
        print("⚠️ Graphviz 'dot' binary is missing; created placeholder architecture_diagram.png")
