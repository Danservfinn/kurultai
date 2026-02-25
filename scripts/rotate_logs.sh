#!/bin/bash
LOG_DIR="/Users/kublai/kurultai/kublai-repo/logs"
MAX_SIZE=10485760  # 10MB
MAX_FILES=5

for logfile in "$LOG_DIR"/*.log; do
    if [ -f "$logfile" ]; then
        size=$(stat -f%z "$logfile" 2>/dev/null || stat -c%s "$logfile" 2>/dev/null)
        if [ "$size" -gt "$MAX_SIZE" ]; then
            # Rotate
            for i in $(seq $MAX_FILES -1 1); do
                if [ -f "$logfile.$i.gz" ]; then
                    mv "$logfile.$i.gz" "$logfile.$((i+1)).gz" 2>/dev/null
                fi
            done
            gzip -c "$logfile" > "$logfile.1.gz"
            > "$logfile"
        fi
    fi
done

# Clean old logs
find "$LOG_DIR" -name "*.log.*.gz" -mtime +7 -delete
