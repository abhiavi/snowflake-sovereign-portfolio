#!/usr/bin/env python3
"""
validate_engine.py
Sovereign Systems Architect - Low-Latency Streaming & Egress Caching Simulator
Simulates high-throughput ZSTD client ingestion and Egress Cost Optimization (ECO) caching routing.
"""

import sys
import os
import time
import json
import socket
import threading
import hashlib
from collections import OrderedDict

# Ensure zstandard is installed
try:
    import zstandard as zstd
    USE_ZSTD = True
except ImportError:
    print("\033[93m[!] zstandard module not found. Attempting automatic installation...\033[0m")
    try:
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "zstandard"])
        import zstandard as zstd
        USE_ZSTD = True
        print("\033[92m[+] zstandard successfully installed and loaded.\033[0m")
    except Exception as e:
        print(f"\033[91m[-] Failed to install zstandard: {e}. Falling back to standard zlib compression.\033[0m")
        import zlib
        USE_ZSTD = False

# Constants for Multi-Cloud Egress Costs ($ per GB)
EGRESS_RATES = {
    "AWS": 0.09,        # $0.09 per GB (S3 to Internet)
    "GCP": 0.12,        # $0.12 per GB (GCS to Internet)
    "Azure": 0.087,     # $0.087 per GB (Blob to Internet)
    "Snowflake": 0.09   # $0.09 per GB (Unload egress)
}

# ANSI Styling Helper
class Style:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

# LRU Cache for ECO Router
class ECORouterCache:
    def __init__(self, capacity: int = 5):
        self.cache = OrderedDict()
        self.capacity = capacity
        self.hits = 0
        self.misses = 0

    def get(self, key: str):
        if key in self.cache:
            self.cache.move_to_end(key)
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None

    def put(self, key: str, value: dict):
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            evicted_key, evicted_val = self.cache.popitem(last=False)
            return evicted_key
        return None

# Compression helper functions
def compress_payload(data: bytes) -> bytes:
    if USE_ZSTD:
        cctx = zstd.ZstdCompressor(level=3)
        return cctx.compress(data)
    else:
        return zlib.compress(data)

def decompress_payload(data: bytes) -> bytes:
    if USE_ZSTD:
        dctx = zstd.ZstdDecompressor()
        return dctx.decompress(data)
    else:
        return zlib.decompress(data)

# Simulated Database/Source for Misses
def fetch_from_cloud(cloud_provider: str, dataset_id: str) -> dict:
    # Simulate database retrieval latency
    time.sleep(0.05)
    dummy_data = {
        "provider": cloud_provider,
        "dataset": dataset_id,
        "records_count": 10000,
        "payload_bytes": 1024 * 1024 * 5,  # 5 MB simulated payload size
        "status": "synchronized"
    }
    return dummy_data

class ServerThread(threading.Thread):
    def __init__(self, host: str, port: int, cache_capacity: int = 5):
        super().__init__()
        self.host = host
        self.port = port
        self.cache = ECORouterCache(capacity=cache_capacity)
        self.running = True
        self.server_socket = None
        self.total_bytes_processed = 0
        self.egress_saved_dollars = 0.0
        self.egress_spent_dollars = 0.0

    def run(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            print(f"{Style.GREEN}[+] Server started on {self.host}:{self.port} with ECO Caching Capacity={self.cache.capacity}{Style.END}")
        except Exception as e:
            print(f"{Style.RED}[-] Server failed to bind to {self.host}:{self.port}: {e}{Style.END}")
            self.running = False
            return

        while self.running:
            try:
                self.server_socket.settimeout(1.0)
                client_sock, addr = self.server_socket.accept()
            except socket.timeout:
                continue
            except Exception:
                break
            
            # Handle incoming client stream
            threading.Thread(target=self.handle_client, args=(client_sock,)).start()

    def handle_client(self, client_sock):
        try:
            while self.running:
                # Read 4 bytes length prefix
                length_bytes = client_sock.recv(4)
                if not length_bytes:
                    break
                payload_len = int.from_bytes(length_bytes, byteorder='big')
                
                # Read payload
                payload = b''
                while len(payload) < payload_len:
                    chunk = client_sock.recv(min(payload_len - len(payload), 4096))
                    if not chunk:
                        break
                    payload += chunk
                
                if len(payload) < payload_len:
                    break

                self.total_bytes_processed += len(payload)
                
                # Decompress
                decompressed = decompress_payload(payload)
                request_data = json.loads(decompressed.decode('utf-8'))
                
                # Extract routing request details
                cloud_provider = request_data.get("cloud_provider", "AWS")
                dataset_id = request_data.get("dataset_id", "default_set")
                
                cache_key = f"{cloud_provider}:{dataset_id}"
                cached_result = self.cache.get(cache_key)
                
                egress_rate = EGRESS_RATES.get(cloud_provider, 0.09)
                
                # Process response & caching cost routing
                if cached_result:
                    # Cache Hit
                    payload_size_gb = cached_result["payload_bytes"] / (1024 * 1024 * 1024)
                    simulated_saving = payload_size_gb * egress_rate
                    self.egress_saved_dollars += simulated_saving
                    
                    response_meta = {
                        "status": "CACHE_HIT",
                        "egress_cost_usd": 0.0,
                        "saving_usd": simulated_saving,
                        "data": cached_result
                    }
                    print(f"{Style.CYAN}[ECO-HIT] Key: {cache_key} | Egress Saving: ${simulated_saving:.6f}{Style.END}")
                else:
                    # Cache Miss - Fetch from simulated provider and route
                    data_fetched = fetch_from_cloud(cloud_provider, dataset_id)
                    payload_size_gb = data_fetched["payload_bytes"] / (1024 * 1024 * 1024)
                    simulated_cost = payload_size_gb * egress_rate
                    self.egress_spent_dollars += simulated_cost
                    
                    evicted = self.cache.put(cache_key, data_fetched)
                    
                    response_meta = {
                        "status": "CACHE_MISS",
                        "egress_cost_usd": simulated_cost,
                        "saving_usd": 0.0,
                        "data": data_fetched
                    }
                    eviction_msg = f" (Evicted: {evicted})" if evicted else ""
                    print(f"{Style.YELLOW}[ECO-MISS] Key: {cache_key} | Incurred Egress: ${simulated_cost:.6f}{eviction_msg}{Style.END}")
                
                # Compress response metadata and send back
                res_bytes = json.dumps(response_meta).encode('utf-8')
                compressed_res = compress_payload(res_bytes)
                client_sock.sendall(len(compressed_res).to_bytes(4, byteorder='big') + compressed_res)
                
        except Exception as e:
            pass
        finally:
            client_sock.close()

    def shutdown(self):
        self.running = False
        if self.server_socket:
            self.server_socket.close()

def run_client_simulation(host: str, port: int):
    # Simulated workloads
    workloads = [
        {"cloud_provider": "AWS", "dataset_id": "user_logs_v1"},
        {"cloud_provider": "AWS", "dataset_id": "user_logs_v1"},  # Hit
        {"cloud_provider": "GCP", "dataset_id": "clickstream_analytics"},
        {"cloud_provider": "Azure", "dataset_id": "finance_records"},
        {"cloud_provider": "GCP", "dataset_id": "clickstream_analytics"},  # Hit
        {"cloud_provider": "Snowflake", "dataset_id": "sales_aggregate_q2"},
        {"cloud_provider": "AWS", "dataset_id": "user_logs_v2"},
        {"cloud_provider": "Azure", "dataset_id": "finance_records"},  # Hit
        {"cloud_provider": "GCP", "dataset_id": "video_metadata"},
        {"cloud_provider": "AWS", "dataset_id": "user_logs_v1"},  # Cache eviction might have happened!
        {"cloud_provider": "Snowflake", "dataset_id": "sales_aggregate_q2"},  # Hit
        {"cloud_provider": "AWS", "dataset_id": "user_logs_v2"},  # Hit
    ]
    
    print(f"\n{Style.HEADER}=== Starting Ingestion Client Workload ==={Style.END}")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((host, port))
    except Exception as e:
        print(f"{Style.RED}[-] Client failed to connect to server: {e}{Style.END}")
        return

    try:
        for idx, work in enumerate(workloads):
            print(f"\n[Client Event {idx+1}/{len(workloads)}] Querying {work['cloud_provider']} - {work['dataset_id']}")
            work_bytes = json.dumps(work).encode('utf-8')
            
            # Compress using ZSTD
            compressed = compress_payload(work_bytes)
            
            # Send length prefixed frame
            sock.sendall(len(compressed).to_bytes(4, byteorder='big') + compressed)
            
            # Receive response
            len_bytes = sock.recv(4)
            if not len_bytes:
                break
            res_len = int.from_bytes(len_bytes, byteorder='big')
            
            res_payload = b''
            while len(res_payload) < res_len:
                chunk = sock.recv(min(res_len - len(res_payload), 4096))
                if not chunk:
                    break
                res_payload += chunk
                
            res_decompressed = decompress_payload(res_payload)
            response = json.loads(res_decompressed.decode('utf-8'))
            
            status = response.get("status")
            status_color = Style.GREEN if status == "CACHE_HIT" else Style.YELLOW
            print(f" -> Response Status: {status_color}{status}{Style.END}")
            if status == "CACHE_HIT":
                print(f" -> Egress Saved: {Style.GREEN}${response.get('saving_usd'):.6f}{Style.END}")
            else:
                print(f" -> Egress Spent: {Style.YELLOW}${response.get('egress_cost_usd'):.6f}{Style.END}")
                
            time.sleep(0.1) # Small throttle for visualization
    finally:
        sock.close()

def main():
    host = "127.0.0.1"
    port = 18085
    
    # Initialize Server
    server = ServerThread(host, port, cache_capacity=4)
    server.start()
    
    # Let server bind
    time.sleep(0.5)
    
    if not server.running:
        print(f"{Style.RED}[-] Aborting simulation due to server startup failure.{Style.END}")
        sys.exit(1)
        
    try:
        run_client_simulation(host, port)
    finally:
        # Give server time to finish last requests
        time.sleep(0.5)
        print(f"\n{Style.HEADER}=== Shutting Down Server ==={Style.END}")
        server.shutdown()
        server.join()
        
    # Visual report
    total_requests = server.cache.hits + server.cache.misses
    hit_ratio = (server.cache.hits / total_requests * 100) if total_requests > 0 else 0.0
    
    baseline_egress_cost = server.egress_spent_dollars + server.egress_saved_dollars
    net_savings = server.egress_saved_dollars
    saving_percentage = (net_savings / baseline_egress_cost * 100) if baseline_egress_cost > 0 else 0.0
    
    print(f"\n{Style.BOLD}{Style.HEADER}=====================================================")
    print("      SOVEREIGN SYSTEM ECO ROUTER AUDIT REPORT       ")
    print(f"====================================================={Style.END}")
    print(f"Compression Protocol : {Style.CYAN}{'ZSTD (Zstandard)' if USE_ZSTD else 'zlib'}{Style.END}")
    print(f"Total Requests Routed: {Style.BOLD}{total_requests}{Style.END}")
    print(f"Cache Hits           : {Style.GREEN}{server.cache.hits}{Style.END}")
    print(f"Cache Misses         : {Style.YELLOW}{server.cache.misses}{Style.END}")
    print(f"ECO Cache Hit Ratio  : {Style.BOLD}{Style.GREEN}{hit_ratio:.2f}%{Style.END}")
    print(f"Total Data Processed : {server.total_bytes_processed} bytes (Socket level)")
    print("-----------------------------------------------------")
    print(f"Baseline Egress Cost : {Style.RED}${baseline_egress_cost:.6f}{Style.END} (No ECO Caching)")
    print(f"Actual Egress Cost   : {Style.YELLOW}${server.egress_spent_dollars:.6f}{Style.END} (With ECO Caching)")
    print(f"Net Egress Savings   : {Style.GREEN}${net_savings:.6f}{Style.END} USD")
    print(f"ECO Efficiency (Cost): {Style.BOLD}{Style.GREEN}{saving_percentage:.2f}% Savings{Style.END}")
    print(f"{Style.BOLD}{Style.HEADER}====================================================={Style.END}\n")

if __name__ == "__main__":
    main()
