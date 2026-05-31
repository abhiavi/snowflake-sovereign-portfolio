#!/usr/bin/env python3
"""
validate_engine.py
================================================================================
Sovereign AI Portfolio - Track 4: RAG & PEFT Validation Engine
--------------------------------------------------------------------------------
This engine simulates semantic chunking pipelines to bypass context limits 
(such as standard 6k token limits), analyzes chunks for context fitting, 
and validates compliance with the Digital Personal Data Protection (DPDP) Act.

Author: Lead Agent (Track 06/08 Infrastructure Manager)
Date: May 2026
License: Sovereign Enterprise
================================================================================
"""

import os
import sys
import re
import argparse
import math
from typing import List, Dict, Any, Tuple

# Terminal coloring codes for premium status reporting
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
UNDERLINE = "\033[4m"
RESET = "\033[0m"

# Sample text containing diverse topics and simulated PII for self-contained validation
DEMO_TEXT = """
Sovereign AI architectures are transforming enterprise data ingestion. By deploying self-hosted LLMs, 
organizations ensure data sovereignty first, aligning with the Ironclad Reliability STP v4.0 mandates. 
We store logs at ~/logs/ and secure all certificates in ~/certs/.
For any questions regarding these infrastructure details, contact the lead admin at abhishek@adraca-mini.tail4f7ccb.ts.net 
or security-alerts@adraca-pve.tailscale.net.
We must prevent information leaks.

Our primary database instances are running on local cluster IPs such as 100.105.27.116 and 100.116.70.21.
These systems hold sensitive metadata. If you require registration access, please present your identity details 
like Aadhaar number 5543-8890-1234 or your Permanent Account Number (PAN) ABCDE1234F.
Additionally, you can contact our security desk at +91 98765 43210 or +1 (555) 019-2834 for escalation.

Parameter-Efficient Fine-Tuning (PEFT) techniques, such as LoRA (Low-Rank Adaptation) and QLoRA, 
allow us to adapt models using minimal compute. Instead of retraining 70B parameter models, 
we freeze the base weights and inject small rank-decomposition matrices. This saves billions in training costs 
and lets us keep processing isolated.
For instance, training a 235B Qwen-thinking model requires massive parallel nodes.
With PEFT, we constraint updates to specific attention layers, achieving comparable performance to full-finetuning.

We enforce strict data pipelines. The RAG ingestion pipeline chunks text semantically by analyzing 
information density and sentence boundaries. If a chunk grows beyond the target block size (e.g., 512 tokens), 
we partition it. This prevents the classic "lost in the middle" phenomenon and avoids exceeding 
restrictive token context windows.
"""

def estimate_tokens(text: str) -> int:
    """Estimates the number of tokens in a text block (approx 1 word = 1.3 tokens)."""
    words = text.split()
    return int(len(words) * 1.3)

def split_into_sentences(text: str) -> List[str]:
    """Splits text into sentences using boundary punctuation regex."""
    sentence_endings = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s')
    sentences = sentence_endings.split(text)
    return [s.strip() for s in sentences if s.strip()]

def get_word_frequencies(text: str) -> Dict[str, int]:
    """Extracts lowercase word frequencies for vector representation (bag of words)."""
    words = re.findall(r'\b\w+\b', text.lower())
    freq = {}
    for w in words:
        # Skip trivial short words/stop words to improve semantic similarity quality
        if len(w) > 2:
            freq[w] = freq.get(w, 0) + 1
    return freq

def cosine_similarity(vec1: Dict[str, int], vec2: Dict[str, int]) -> float:
    """Calculates cosine similarity between two word frequency vectors."""
    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum([vec1[x] * vec2[x] for x in intersection])
    
    sum1 = sum([vec1[x]**2 for x in vec1.keys()])
    sum2 = sum([vec2[x]**2 for x in vec2.keys()])
    
    denominator = math.sqrt(sum1) * math.sqrt(sum2)
    
    if not denominator:
        return 0.0
    return float(numerator) / denominator

class SemanticChunker:
    """
    Performs semantic chunking by analyzing local cosine similarity drop-offs 
    between sliding window text sentences. Automatically prevents chunks from 
    exceeding token limits.
    """
    def __init__(self, threshold: float = 0.25, max_tokens: int = 200, window_size: int = 1):
        self.threshold = threshold
        self.max_tokens = max_tokens
        self.window_size = window_size

    def chunk(self, text: str) -> List[Dict[str, Any]]:
        sentences = split_into_sentences(text)
        if not sentences:
            return []

        # Vectorize sentences
        vectors = [get_word_frequencies(s) for s in sentences]
        
        # Calculate similarities between adjacent sentence windows
        similarities = []
        for i in range(len(sentences) - 1):
            left_window_text = " ".join(sentences[max(0, i - self.window_size + 1):i + 1])
            right_window_text = " ".join(sentences[i + 1:min(len(sentences), i + 1 + self.window_size)])
            
            vec_l = get_word_frequencies(left_window_text)
            vec_r = get_word_frequencies(right_window_text)
            
            sim = cosine_similarity(vec_l, vec_r)
            similarities.append(sim)

        chunks = []
        current_chunk_sentences = []
        current_tokens = 0
        
        for i, sentence in enumerate(sentences):
            sent_tokens = estimate_tokens(sentence)
            
            # Check if adding this sentence exceeds maximum token size
            if current_chunk_sentences and (current_tokens + sent_tokens > self.max_tokens):
                chunk_text = " ".join(current_chunk_sentences)
                chunks.append({
                    "text": chunk_text,
                    "tokens": current_tokens,
                    "sentences_count": len(current_chunk_sentences),
                    "split_reason": f"LIMIT_EXCEEDED (Max: {self.max_tokens} tokens)"
                })
                current_chunk_sentences = []
                current_tokens = 0

            current_chunk_sentences.append(sentence)
            current_tokens += sent_tokens

            # Check if we should split after this sentence based on semantic similarity
            if i < len(similarities):
                sim = similarities[i]
                if sim < self.threshold:
                    chunk_text = " ".join(current_chunk_sentences)
                    chunks.append({
                        "text": chunk_text,
                        "tokens": current_tokens,
                        "sentences_count": len(current_chunk_sentences),
                        "split_reason": f"SEMANTIC_BOUNDARY (Sim: {sim:.3f} < Thresh: {self.threshold:.3f})"
                    })
                    current_chunk_sentences = []
                    current_tokens = 0

        # Append last remaining chunk
        if current_chunk_sentences:
            chunk_text = " ".join(current_chunk_sentences)
            chunks.append({
                "text": chunk_text,
                "tokens": current_tokens,
                "sentences_count": len(current_chunk_sentences),
                "split_reason": "END_OF_DOCUMENT"
            })

        return chunks

class DPDPValidator:
    """
    Enforces compliance with the Indian Digital Personal Data Protection (DPDP) Act.
    Identifies PII anomalies and computes compliance indexes.
    """
    # Regex expressions targeting critical PII fields (both global and local to Indian context)
    PII_PATTERNS = {
        "EMAIL_ADDRESS": r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}',
        "PHONE_NUMBER": r'\b(?:\+?\d{1,3}[- ]?)?\(?\d{3}\)?[- ]?\d{3,4}[- ]?\d{4}\b',
        "AADHAAR_NUMBER": r'\b\d{4}[- ]?\d{4}[- ]?\d{4}\b',
        "PAN_CARD": r'\b[A-Z]{5}[0-9]{4}[A-Z]{1}\b',
        "IP_ADDRESS": r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b',
    }

    @classmethod
    def audit(cls, text: str) -> Dict[str, Any]:
        findings = {}
        total_violations = 0
        
        for pii_name, pattern in cls.PII_PATTERNS.items():
            matches = re.findall(pattern, text)
            if matches:
                findings[pii_name] = {
                    "count": len(matches),
                    "matches": list(set(matches))
                }
                total_violations += len(matches)
        
        # Calculate DPDP Compliance Index: 100% base, deduct 15% per unique violation class, min 0%
        deduction = len(findings) * 20.0
        compliance_score = max(0.0, 100.0 - deduction)
        
        return {
            "compliant": total_violations == 0,
            "compliance_score": compliance_score,
            "violations_count": total_violations,
            "findings": findings
        }

    @classmethod
    def sanitize(cls, text: str) -> str:
        sanitized = text
        for pii_name, pattern in cls.PII_PATTERNS.items():
            sanitized = re.sub(pattern, f"<REDACTED_{pii_name}>", sanitized)
        return sanitized

def run_pipeline(text: str, threshold: float, max_tokens: int, window_size: int, redact: bool) -> None:
    print(f"\n{BOLD}{CYAN}=== Starting Sovereign AI RAG & PEFT Validation Pipeline ==={RESET}")
    print(f"Config: threshold={threshold}, max_tokens={max_tokens}, window_size={window_size}, redact={redact}\n")
    
    # Init engines
    chunker = SemanticChunker(threshold=threshold, max_tokens=max_tokens, window_size=window_size)
    
    raw_tokens = estimate_tokens(text)
    print(f"{BOLD}Raw Input Document stats:{RESET}")
    print(f"  - Characters: {len(text)}")
    print(f"  - Sentences : {len(split_into_sentences(text))}")
    print(f"  - Estimated Tokens: {raw_tokens}")
    print("-" * 80)
    
    # Run Chunker
    chunks = chunker.chunk(text)
    
    print(f"\n{BOLD}{GREEN}Generated {len(chunks)} Semantic Chunks:{RESET}\n")
    
    non_compliant_chunks = 0
    
    for idx, chunk in enumerate(chunks, 1):
        chunk_text = chunk["text"]
        tokens = chunk["tokens"]
        reason = chunk["split_reason"]
        
        # Verify chunk size limits
        size_status = f"{GREEN}OK{RESET}" if tokens <= max_tokens else f"{RED}LIMIT_EXCEEDED{RESET}"
        
        # Verify DPDP Compliance
        audit_res = DPDPValidator.audit(chunk_text)
        compliance_status = f"{GREEN}COMPLIANT (100%){RESET}"
        if not audit_res["compliant"]:
            compliance_status = f"{RED}NON-COMPLIANT ({audit_res['compliance_score']}%){RESET}"
            non_compliant_chunks += 1
            
        print(f"{BOLD}{BLUE}--- Chunk #{idx} ({tokens} tokens) [{size_status}] ---{RESET}")
        print(f"Split Reason : {reason}")
        print(f"Compliance   : {compliance_status}")
        
        if redact and not audit_res["compliant"]:
            display_text = DPDPValidator.sanitize(chunk_text)
            print(f"{YELLOW}Sanitized Text (Redacted for Compliance):{RESET}")
        else:
            display_text = chunk_text
            if not audit_res["compliant"]:
                print(f"{RED}PII Violations Detected:{RESET}")
                for pii_type, info in audit_res["findings"].items():
                    print(f"  * {pii_type}: Found {info['count']} occurrence(s) -> {info['matches']}")
            print(f"Text Content :")
            
        # Format text to wrap nicely in CLI
        wrapped = "\n".join(["    " + line.strip() for line in display_text.split("\n") if line.strip()])
        print(wrapped)
        print()

    print("-" * 80)
    print(f"{BOLD}Pipeline Summary:{RESET}")
    print(f"  - Input Size : {raw_tokens} tokens")
    print(f"  - Chunk Count: {len(chunks)}")
    print(f"  - Max Limit  : {max_tokens} tokens per chunk")
    print(f"  - Compliant Chunks: {len(chunks) - non_compliant_chunks} / {len(chunks)}")
    if non_compliant_chunks > 0:
        print(f"  - DPDP Status: {RED}WARNING - PII Detected in {non_compliant_chunks} chunks.{RESET}")
        if redact:
            print(f"  - Remediation: {GREEN}SUCCESS - Auto-redacted PII output pipelines.{RESET}")
        else:
            print(f"  - Remediation: {YELLOW}Action Required - Run with --redact flag to sanitize output.{RESET}")
    else:
        print(f"  - DPDP Status: {GREEN}SECURE - No PII Violations.{RESET}")
    print(f"{BOLD}{CYAN}=== Pipeline Finished ==={RESET}\n")

def main():
    parser = argparse.ArgumentParser(
        description="Sovereign AI Portfolio RAG/PEFT Semantic Chunking & DPDP Validation Tool",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("-f", "--file", type=str, help="Path to input text file. If omitted, demo text is used.")
    parser.add_argument("-t", "--threshold", type=float, default=0.25, help="Cosine similarity threshold for semantic breaks")
    parser.add_argument("-m", "--max-tokens", type=int, default=150, help="Maximum allowed tokens per chunk to bypass 6k limit constraints")
    parser.add_argument("-w", "--window", type=int, default=1, help="Sliding window size for smoothing chunk similarity comparisons")
    parser.add_argument("-r", "--redact", action="store_true", help="Auto-redact PII to align with DPDP compliance mandates")
    
    args = parser.parse_args()
    
    input_text = DEMO_TEXT
    if args.file:
        if not os.path.exists(args.file):
            print(f"{RED}Error: File '{args.file}' not found.{RESET}", file=sys.stderr)
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            input_text = f.read()
            
    run_pipeline(
        text=input_text, 
        threshold=args.threshold, 
        max_tokens=args.max_tokens, 
        window_size=args.window, 
        redact=args.redact
    )

if __name__ == "__main__":
    main()
