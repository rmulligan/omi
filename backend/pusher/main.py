import json
import logging
import os

logging.basicConfig(level=logging.INFO)

# Stub: skip Firebase initialization for local development.
# The pusher's WebSocket handler uses stubbed database functions that
# return defaults instead of querying Firestore.

import os

from fastapi import FastAPI
from routers import pusher, metrics
from utils.http_client import close_all_clients

app = FastAPI()
app.include_router(pusher.router)
app.include_router(metrics.router)

paths = ['_temp', '_samples', '_segments', '_speech_profiles']
for path in paths:
    if not os.path.exists(path):
        os.makedirs(path)


@app.on_event("shutdown")
async def shutdown_event():
    await close_all_clients()


@app.get('/health')
async def health_check():
    return {"status": "healthy"}
