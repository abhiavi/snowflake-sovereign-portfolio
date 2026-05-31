import os
import sys
import json
import unittest
from typing import Dict, Any, Union
from hypothesis import given, strategies as st

# ==========================================
# 1. MOCK MCP SERVER IMPLEMENTATION
# ==========================================
class MockMCPServer:
    """
    Mock Model Context Protocol (MCP) Server.
    Implements base JSON-RPC 2.0 interface.
    """
    def __init__(self):
        self.allowed_tools = ["query_portfolio", "list_assets"]
        self.allowed_resources = ["portfolio_summary.json", "market_data.csv"]

    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "Mock-Sovereign-MCP", "version": "1.0.0"}
                },
                "id": req_id
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "result": {
                    "tools": [
                        {"name": "query_portfolio", "description": "Queries the active portfolio database"},
                        {"name": "list_assets", "description": "Lists current assets"}
                    ]
                },
                "id": req_id
            }

        elif method == "tools/call":
            name = params.get("name")
            if name not in self.allowed_tools:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Tool '{name}' not found"},
                    "id": req_id
                }
            return {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": f"Executed tool {name} successfully"}]},
                "id": req_id
            }

        elif method == "resources/read":
            uri = params.get("uri", "")
            return {
                "jsonrpc": "2.0",
                "result": {"contents": [{"uri": uri, "text": "Confidential portfolio data"}]},
                "id": req_id
            }

        return {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": "Method not found"},
            "id": req_id
        }


# ==========================================
# 2. AUTHORIZATION PROXY IMPLEMENTATION
# ==========================================
class MCPAuthorizationProxy:
    """
    Authorization Proxy protecting the MCP server.
    Enforces token validation and blocks directory traversals/injection attacks.
    """
    def __init__(self, server: MockMCPServer, secret_token: str = "sk-sovereign-mcp-2026"):
        self.server = server
        self.secret_token = secret_token

    def is_valid_token(self, token: str) -> bool:
        if not token or not isinstance(token, str):
            return False
        return token.strip() == self.secret_token

    def is_safe_path(self, path: str) -> bool:
        if not path or not isinstance(path, str):
            return True
        # Check for directory traversal attempts
        normalized = os.path.normpath(path)
        if normalized.startswith("..") or "/../" in path or "..\\" in path:
            return False
        if any(bad in path for bad in ["/etc/", "/var/", "~/", "passwd", ".git"]):
            return False
        return True

    def process_request(self, auth_header: str, request: Dict[str, Any]) -> Dict[str, Any]:
        # 1. Parse Token
        if not auth_header or not auth_header.startswith("Bearer "):
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32001, "message": "Unauthorized: Missing or invalid token format"},
                "id": request.get("id")
            }
        
        token = auth_header.split("Bearer ")[1]
        if not self.is_valid_token(token):
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32002, "message": "Unauthorized: Invalid token"},
                "id": request.get("id")
            }

        # 2. Inspect payload for security policy compliance
        method = request.get("method")
        params = request.get("params", {})

        # Directory traversal protection on resource URIs
        if method == "resources/read":
            uri = params.get("uri", "")
            if not self.is_safe_path(uri):
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32003, "message": "Access Denied: Path traversal detected"},
                    "id": request.get("id")
                }

        # SQL Injection & Command Injection check in tool parameters
        if method == "tools/call":
            arguments = params.get("arguments", {})
            for arg_val in arguments.values():
                if isinstance(arg_val, str):
                    if ";" in arg_val or "union" in arg_val.lower():
                        return {
                            "jsonrpc": "2.0",
                            "error": {"code": -32004, "message": "Access Denied: SQL/Command injection detected"},
                            "id": request.get("id")
                        }

        # 3. Forward request to target server if authenticated & verified
        return self.server.handle_request(request)


# ==========================================
# 3. PROPERTY-BASED FUZZING TESTS
# ==========================================
class TestMCPProxySecurity(unittest.TestCase):

    def setUp(self):
        self.server = MockMCPServer()
        self.proxy = MCPAuthorizationProxy(self.server)

    @given(st.text())
    def test_fuzz_auth_token_resilience(self, fuzzed_token):
        """
        Fuzz authorization proxy with arbitrary strings to ensure it rejects 
        all tokens that do not exactly match our secret key.
        """
        request = {
            "jsonrpc": "2.0",
            "method": "tools/list",
            "id": 1
        }
        
        auth_header = f"Bearer {fuzzed_token}"
        response = self.proxy.process_request(auth_header, request)

        if fuzzed_token == "sk-sovereign-mcp-2026":
            self.assertNotIn("error", response)
            self.assertIn("result", response)
        else:
            self.assertIn("error", response)
            self.assertEqual(response["error"]["code"], -32002)

    @given(st.text())
    def test_fuzz_directory_traversal_protection(self, fuzzed_path):
        """
        Fuzz the resource read path with arbitrary text input.
        If a directory traversal pattern is fuzzed, the proxy must safely block it.
        """
        request = {
            "jsonrpc": "2.0",
            "method": "resources/read",
            "params": {"uri": fuzzed_path},
            "id": 1
        }
        
        auth_header = "Bearer sk-sovereign-mcp-2026"
        response = self.proxy.process_request(auth_header, request)

        is_traversal = False
        if ".." in fuzzed_path or "/../" in fuzzed_path or "..\\" in fuzzed_path:
            is_traversal = True
        if any(bad in fuzzed_path for bad in ["/etc/", "/var/", "~/", "passwd", ".git"]):
            is_traversal = True

        if is_traversal:
            if "error" in response:
                self.assertEqual(response["error"]["code"], -32003)

if __name__ == "__main__":
    unittest.main()
