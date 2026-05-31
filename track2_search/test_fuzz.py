import os
import sys
import unittest
from hypothesis import given, strategies as st
from fastapi.testclient import TestClient

# Ensure current directory is in path to import local module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_engine import app

client = TestClient(app)

class TestCortexSecurityFuzzing(unittest.TestCase):
    
    @given(
        q=st.text(min_size=0, max_size=1000),
        token=st.one_of(
            st.just("token-public"),
            st.just("token-finance"),
            st.just("token-hr"),
            st.just("token-admin"),
            st.none(),
            st.text(alphabet=st.characters(max_codepoint=127), min_size=1, max_size=100) # Arbitrary/random ASCII tokens
        )
    )
    def test_security_invariant(self, q, token):
        """
        Property-Based Invariant:
        No document returned in 'pre-filter' mode should have a security tag
        outside of the validated authorization scopes.
        """
        headers = {}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
            
        response = client.get("/search", params={"q": q, "filter_mode": "pre-filter"}, headers=headers)
        
        # If token is invalid, it must return a 401 Unauthorized.
        if response.status_code == 401:
            return
            
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        # Determine permitted roles for this token
        if token is None:
            allowed_roles = {"PUBLIC"}
        elif token == "token-admin":
            allowed_roles = {"PUBLIC", "HR", "FINANCE"}
        elif token == "token-hr":
            allowed_roles = {"PUBLIC", "HR"}
        elif token == "token-finance":
            allowed_roles = {"PUBLIC", "FINANCE"}
        elif token == "token-public":
            allowed_roles = {"PUBLIC"}
        else:
            # Any arbitrary token should have failed with a 401 response.
            self.fail(f"Invalid token '{token}' did not trigger a 401 status code.")
            
        for doc in data:
            self.assertIn(
                doc["security_tag"], 
                allowed_roles, 
                f"SECURITY VIOLATION: Document {doc['id']} (Tag: {doc['security_tag']}) leaked to unauthorized token '{token}'!"
            )

if __name__ == "__main__":
    unittest.main()
