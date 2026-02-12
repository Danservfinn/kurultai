import os
import sys
import json
import asyncio
import aiohttp
import logging
import traceback
from datetime import datetime

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("kurultai-ultra-debug")

async def debug_bot():
    from dotenv import load_dotenv
    load_dotenv()
    
    token = os.getenv("KUBLAI_DISCORD_TOKEN")
    channel_id = os.getenv("DISCORD_COUNCIL_CHANNEL_ID")
    
    logger.info(f"Starting ultra-debug bot")
    logger.info(f"Channel ID: {channel_id}")
    
    session = aiohttp.ClientSession()
    
    # Get gateway
    async with session.get("https://discord.com/api/v10/gateway", headers={"Authorization": f"Bot {token}"}) as resp:
        data = await resp.json()
        gateway_url = data.get("url")
        logger.info(f"Gateway URL: {gateway_url}")
    
    # Connect WebSocket
    ws = await session.ws_connect(f"{gateway_url}/?v=10&encoding=json")
    logger.info("WebSocket connected")
    
    # Get hello
    msg = await ws.receive_json()
    logger.info(f"Hello received: {msg.get('op')}")
    heartbeat_interval = msg["d"]["heartbeat_interval"] / 1000
    
    # Start heartbeat
    async def heartbeat():
        while True:
            await asyncio.sleep(heartbeat_interval)
            await ws.send_json({"op": 1, "d": None})
            logger.debug("Heartbeat sent")
    asyncio.create_task(heartbeat())
    
    # Identify with all intents
    intents = (1 << 9) | (1 << 15)  # Guild messages + Message content
    logger.info(f"Identifying with intents: {intents} (bits 9 + 15)")
    
    await ws.send_json({
        "op": 2,
        "d": {
            "token": token,
            "intents": intents,
            "properties": {"os": "linux", "browser": "DebugBot", "device": "DebugBot"}
        }
    })
    
    # Listen for ALL events
    async for msg in ws:
        if msg.type == aiohttp.WSMsgType.TEXT:
            data = json.loads(msg.data)
            op = data.get("op")
            event_type = data.get("t")
            
            if event_type:
                logger.info(f"📨 EVENT: {event_type}")
                
                if event_type == "READY":
                    logger.info(f"✅ Bot ready: {data['d']['user']['username']}")
                    
                elif event_type == "MESSAGE_CREATE":
                    d = data["d"]
                    logger.info(f"💬 MESSAGE from {d['author']['username']}: {d.get('content', 'NO CONTENT')[:100]}")
                    logger.info(f"   Channel: {d.get('channel_id')} (expected: {channel_id})")
                    logger.info(f"   Is bot: {d['author'].get('bot', False)}")
                    logger.info(f"   Full content present: {'content' in d and d['content']}")
                    
                    # Check if this is our channel and not a bot
                    if d.get("channel_id") == channel_id and not d["author"].get("bot", False):
                        logger.info("🎯 MATCH! This message should trigger a response!")
                        
            elif op == 11:
                logger.debug("Heartbeat ACK")
        elif msg.type == aiohttp.WSMsgType.ERROR:
            logger.error(f"WebSocket error: {ws.exception()}")

asyncio.run(debug_bot())
