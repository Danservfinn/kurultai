#!/usr/bin/env python3
"""Fix cron job model names"""
import json

def main():
    with open("/Users/kublai/.openclaw/cron/jobs.json", "r") as f:
        data = json.load(f)

    for job in data["jobs"]:
        if "payload" in job and "model" in job["payload"]:
            current = job["payload"]["model"]
            # Fix the specific model names
            if current == "ollama/hf.co/lukey03/Qwen3.5-9B-abliterated-GGUF":
                job["payload"]["model"] = "qwen3.5:9b"
                print(f"Fixed: {job['name']}: ollama/hf.co/... -> qwen3.5:9b")
            elif current.startswith("ollama/"):
                # Remove ollama/ prefix
                job["payload"]["model"] = current.replace("ollama/", "")
                print(f"Fixed: {job['name']}: {current} -> {job['payload']['model']}")

    with open("/Users/kublai/.openclaw/cron/jobs.json", "w") as f:
        json.dump(data, f, indent=2)

    print("All done")

if __name__ == "__main__":
    main()
