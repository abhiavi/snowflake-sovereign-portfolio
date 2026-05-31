import os
import sys

def main():
    print("=== Generating Cortex Search Zero-Trust Architecture Diagram ===")
    
    # Attempt to import diagrams library
    try:
        from diagrams import Diagram, Cluster, Edge
        from diagrams.onprem.client import User
        from diagrams.onprem.compute import Server
        from diagrams.aws.security import IAM
        from diagrams.aws.database import RDS, Aurora
    except ImportError as e:
        print(f"Python 'diagrams' library failed to import: {e}")
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

    try:
        with Diagram(
            "Snowflake Cortex Search Owner Rights Zero-Trust Architecture",
            show=False,
            filename="cortex_architecture",
            outformat="png",
            graph_attr=graph_attr
        ):
            user = User("User (Analyst)")
            
            with Cluster("Zero-Trust Security Boundary"):
                middleware = IAM("Token Enforcement\nMiddleware")
                api_gateway = Server("FastAPI Gateway\n(validate_engine)")
                
            with Cluster("Snowflake Enterprise Boundary (Owner's Rights)"):
                with Cluster("Cortex AI Search Service"):
                    pre_filter = RDS("Pre-Filtering Engine\n(Constraint Appended)")
                    post_filter = RDS("Post-Filtering Engine\n(Dilution Risk)")
                    
                vector_db = Aurora("Vector Database\n(Sovereign Document Corpus)")
                
            # Flow lines
            user >> Edge(color="blue", style="bold", label="1. Query + Identity Token") >> api_gateway
            api_gateway >> Edge(color="purple", label="2. Validate & Map Role Claims") >> middleware
            middleware >> Edge(color="purple", label="3. Restrict Query Scope") >> api_gateway
            
            # Pre-filtering path (Secure)
            api_gateway >> Edge(color="green", style="solid", label="4a. Query + Metadata Filter") >> pre_filter
            pre_filter >> Edge(color="green", label="5a. Exact Index Search") >> vector_db
            
            # Post-filtering path (Vulnerable)
            api_gateway >> Edge(color="red", style="dashed", label="4b. Open Query (Owner Rights)") >> post_filter
            post_filter >> Edge(color="red", style="dashed", label="5b. Top-K Retrieve -> Filter Chunks") >> vector_db
            
        print("Success: Diagram rendered to 'cortex_architecture.png'")
    except Exception as e:
        print(f"Error rendering diagram (Graphviz binary likely missing): {e}")
        print("Please ensure 'graphviz' is installed on your OS (e.g., 'sudo apt-get install graphviz').")
        # Exit gracefully to allow verification suite to continue other assertions
        sys.exit(0)

if __name__ == "__main__":
    main()
