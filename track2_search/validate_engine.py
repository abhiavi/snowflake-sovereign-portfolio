import os
import sqlite3
from typing import List, Optional
from fastapi import FastAPI, Depends, Header, HTTPException, status
from pydantic import BaseModel

# Initialize FastAPI App
app = FastAPI(
    title="Sovereign Token Enforcement Middleware (Cortex AI Search Mitigation)",
    description="Simulates Zero-Trust pre-filtering to mitigate Cortex Search Owner Rights privilege escalation.",
    version="1.0.0"
)

DB_PATH = "cortex_simulator.db"

# Pydantic Schemas
class SearchResult(BaseModel):
    id: int
    title: str
    content: str
    security_tag: str
    relevance_score: float

class DocumentCreate(BaseModel):
    title: str
    content: str
    security_tag: str

# Database Initialization & Seed Data
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            security_tag TEXT NOT NULL
        )
    """)
    
    # Check if empty, then seed
    cursor.execute("SELECT COUNT(*) FROM documents")
    if cursor.fetchone()[0] == 0:
        seed_data = [
            ("Q3 Financial Strategy & Budget Allocations", 
             "Confidential: Our target is to expand Snowflake footprint by 40% with a budget of $12M under code-name Supernova.", 
             "FINANCE"),
            ("Employee Performance Review Guidelines 2026", 
             "Restricted: Salary increases and review rankings are managed via Workday. Standard scale is 1-5.", 
             "HR"),
            ("Snowflake Cortex Search Architecture Overview", 
             "Public: Cortex Search provides low-latency search. Important: Services run with OWNER rights, necessitating middleware-level token filtering.", 
             "PUBLIC"),
            ("Enterprise Public Knowledgebase", 
             "Public: Welcome to the Sovereign Fleet workspace. All non-sensitive infrastructure mappings are available here.", 
             "PUBLIC"),
            ("M&A Strategy Outline", 
             "Highly Confidential: Potential acquisition of target assets valued at $4.5M in Q4.", 
             "FINANCE")
        ]
        cursor.executemany("INSERT INTO documents (title, content, security_tag) VALUES (?, ?, ?)", seed_data)
        conn.commit()
    conn.close()

# Initialize DB on startup
init_db()

# Simulated Token & Role Resolution
# In production, this would validate JWT claims from the Authorization header.
def resolve_user_roles(authorization: Optional[str] = Header(None)) -> List[str]:
    if not authorization:
        # Default to PUBLIC if no auth token is provided
        return ["PUBLIC"]
    
    # Simple simulated token validation mapping
    token = authorization.replace("Bearer ", "").strip()
    if token == "token-admin":
        return ["PUBLIC", "HR", "FINANCE"]
    elif token == "token-hr":
        return ["PUBLIC", "HR"]
    elif token == "token-finance":
        return ["PUBLIC", "FINANCE"]
    elif token == "token-public":
        return ["PUBLIC"]
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Sovereign Identity Token."
        )

# Simple TF-IDF/Keyword scoring for relevance simulation
def compute_relevance(query: str, text: str) -> float:
    query_words = {q.strip(".,;:!?()\"'") for q in query.lower().split() if q.strip(".,;:!?()\"'")}
    text_words = [w.strip(".,;:!?()\"'") for w in text.lower().split()]
    text_words = [w for w in text_words if w]
    if not text_words:
        return 0.0
    matches = sum(1 for word in text_words if word in query_words)
    return round((matches / len(text_words)) * 10.0, 2)

@app.get("/search", response_model=List[SearchResult])
def search(
    q: str, 
    filter_mode: str = "pre-filter", 
    roles: List[str] = Depends(resolve_user_roles)
):
    """
    Search endpoint simulating Cortex AI Search.
    
    - filter_mode = "pre-filter" (Secure): Appends security tags as query metadata predicates before matching.
    - filter_mode = "post-filter" (Vulnerable to Dilution): Runs search first, then filters results in memory.
    - filter_mode = "no-filter" (Vulnerable - Owner Rights Leak): Returns all documents matching keywords regardless of role.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Pre-filtering implementation (Secure Zero-Trust Pattern)
    if filter_mode == "pre-filter":
        # The query is constrained to only the tags the user is authorized to view.
        placeholders = ",".join("?" for _ in roles)
        query_sql = f"SELECT id, title, content, security_tag FROM documents WHERE security_tag IN ({placeholders})"
        cursor.execute(query_sql, roles)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            doc_id, title, content, security_tag = row
            score = compute_relevance(q, content) + compute_relevance(q, title)
            if score > 0 or q == "*":
                results.append(SearchResult(
                    id=doc_id,
                    title=title,
                    content=content,
                    security_tag=security_tag,
                    relevance_score=score
                ))
        # Sort by score descending
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        conn.close()
        return results

    # 2. Post-filtering implementation (Demonstrates KNN Dilution risk)
    elif filter_mode == "post-filter":
        # Query all documents (simulates OWNER rights retrieve step)
        cursor.execute("SELECT id, title, content, security_tag FROM documents")
        rows = cursor.fetchall()
        
        all_results = []
        for row in rows:
            doc_id, title, content, security_tag = row
            score = compute_relevance(q, content) + compute_relevance(q, title)
            if score > 0 or q == "*":
                all_results.append({
                    "id": doc_id,
                    "title": title,
                    "content": content,
                    "security_tag": security_tag,
                    "score": score
                })
        
        # Sort and take top N (simulating Vector Search returning top results first)
        all_results.sort(key=lambda x: x["score"], reverse=True)
        top_k = all_results[:2]
        
        # Post-filter step: filter down the top results to only what the user has role access to
        filtered_results = []
        for doc in top_k:
            if doc["security_tag"] in roles:
                filtered_results.append(SearchResult(
                    id=doc["id"],
                    title=doc["title"],
                    content=doc["content"],
                    security_tag=doc["security_tag"],
                    relevance_score=doc["score"]
                ))
        conn.close()
        return filtered_results

    # 3. No-filtering implementation (Owner Rights Leak)
    elif filter_mode == "no-filter":
        cursor.execute("SELECT id, title, content, security_tag FROM documents")
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            doc_id, title, content, security_tag = row
            score = compute_relevance(q, content) + compute_relevance(q, title)
            if score > 0 or q == "*":
                results.append(SearchResult(
                    id=doc_id,
                    title=title,
                    content=content,
                    security_tag=security_tag,
                    relevance_score=score
                ))
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        conn.close()
        return results

    else:
        conn.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filter_mode. Choose 'pre-filter', 'post-filter', or 'no-filter'."
        )

@app.post("/documents", response_model=DocumentCreate, status_code=status.HTTP_201_CREATED)
def create_document(doc: DocumentCreate, authorization: Optional[str] = Header(None)):
    # Only Admin token can insert new documents
    roles = resolve_user_roles(authorization)
    if "HR" not in roles or "FINANCE" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only Admin identities can ingest documents."
        )
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO documents (title, content, security_tag) VALUES (?, ?, ?)",
        (doc.title, doc.content, doc.security_tag)
    )
    conn.commit()
    conn.close()
    return doc

if __name__ == "__main__":
    import uvicorn
    # Start the server on port 10005 to abide by Port Guard rules (>10000)
    uvicorn.run(app, host="127.0.0.1", port=10005)
