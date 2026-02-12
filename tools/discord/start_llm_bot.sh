#!/bin/bash
# Legacy script - redirects to main bot launcher
# The bot now uses LLM-powered responses by default

cd /data/workspace/souls/main
./tools/discord/start_bot.sh "$@"
