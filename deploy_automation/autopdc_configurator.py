#!/usr/bin/env python3
import subprocess
import sys
import signal
import os
import time

RUNTIME_FILE = "runtime.log"

def run_command(cmd):
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")  

    process.wait()
    return process.returncode
        
def format_hms(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours}h {minutes}m {secs:05.2f}s"
    elif minutes > 0:
        return f"{minutes}m {secs:05.2f}s"
    else:
        return f"{secs:05.2f}s"

def write_runtime(label, seconds):
    formatted = format_hms(seconds)
    with open(RUNTIME_FILE, "a") as f:
        f.write(f"{label:<20} {formatted}\n")
    
def main():
    if len(sys.argv) != 2:
        print(f"Uso: {sys.argv[0]} <config.json>")
        sys.exit(1)

    json_path = sys.argv[1]

    if not os.path.isfile(json_path):
        print(f"❌ JSON file not found: {json_path}")
        sys.exit(1)

    with open(RUNTIME_FILE, "w") as f:
        f.write("=== Runtime summary ===\n")
        
    steps = [
        (["bash", "deployer.sh", json_path], "Deployer"),
        (["python3", "applier.py", json_path], "Applier")
    ]

    total_start = time.perf_counter()
    for cmd, label in steps:
        print(f"\n🚀 Execute {label}: {' '.join(cmd)}\n")

        start = time.perf_counter()
        code = run_command(cmd)
        end = time.perf_counter()

        elapsed = end - start
        write_runtime(label, elapsed)
        
        if code != 0:
            print(f"\n❌ {label} failed with exit code {code}. Aborting.")
            sys.exit(code)

        print(f"\n✅ {label} completed successfully!\n")

    total_end = time.perf_counter()
    total_elapsed = total_end - total_start
    formatted_total = format_hms(total_elapsed)
    print(f"\n🎉 All completed without errors in {formatted_total}!\n")


if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(1))     # Clean CTRL-C handling
    main()
