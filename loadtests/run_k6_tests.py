import subprocess
import json
import datetime
import os

SHORT_CODE = "cEhtRPZ"
DATE = datetime.datetime.now().strftime("%Y-%m-%d")
RESULTS_FILE = "loadtests/RESULTS.md"

def update_markdown(row):
    with open(RESULTS_FILE, "r") as f:
        content = f.read()
    
    parts = content.split("## Performance Tuning Log")
    new_content = parts[0] + row + "\n## Performance Tuning Log" + parts[1]
    
    with open(RESULTS_FILE, "w") as f:
        f.write(new_content)

print("Starting 4 k6 load tests...")
for i in range(1, 5):
    print(f"Running test {i}...")
    export_file = f"summary_{i}.json"
    
    # Run k6
    cmd = [
        "k6", "run", 
        f"--summary-export={export_file}", 
        "--summary-trend-stats=avg,min,med,max,p(90),p(95),p(99)", 
        "-e", f"SHORT_CODE={SHORT_CODE}", 
        "loadtests/redirect_test.js"
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Parse json
    with open(export_file, "r") as f:
        data = json.load(f)
        
    metrics = data["metrics"]
    rps = metrics["http_reqs"]["rate"]
    p50 = metrics["http_req_duration"]["med"]
    p95 = metrics["http_req_duration"]["p(95)"]
    p99 = metrics["http_req_duration"]["p(99)"]
    error_rate = metrics["http_req_failed"]["value"]
    
    rps_str = f"{rps:.0f}"
    p50_str = f"{p50:.1f}ms"
    p95_str = f"{p95:.1f}ms"
    p99_str = f"{p99:.1f}ms"
    error_pct = f"{error_rate * 100:.2f}%"
    
    row = f"| {DATE} | 500 VUs, k6 (Run {i}) | {rps_str} | {p50_str} | {p95_str} | {p99_str} | {error_pct} | Uncapped Stress Test |"
    update_markdown(row)
    
    os.remove(export_file)

print("All tests finished!")
