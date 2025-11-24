#!/usr/bin/env python3
import subprocess
import sys
import signal
import os

def run_command(cmd):
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )

    for line in process.stdout:
        print(line, end="")  # live stamp

    process.wait()
    return process.returncode


def main():
    # Check arguments
    if len(sys.argv) != 2:
        print(f"Uso: {sys.argv[0]} <config.json>")
        sys.exit(1)

    json_path = sys.argv[1]

    # Check file existence
    if not os.path.isfile(json_path):
        print(f"❌ JSON file not found: {json_path}")
        sys.exit(1)

    steps = [
        (["bash", "deployer.sh", json_path], "Deployer"),
        (["python3", "applier.py", json_path], "Applier")
    ]

    for cmd, label in steps:
        print(f"\n🚀 Execute {label}: {' '.join(cmd)}\n")

        code = run_command(cmd)

        if code != 0:
            print(f"\n❌ {label} failed with exit code {code}. Aborting.")
            sys.exit(code)

        print(f"\n✅ {label} completed successfully!\n")

    print("\n🎉 All completed without errors!\n")


if __name__ == "__main__":
    # Clean CTRL-C handling
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(1))
    main()
