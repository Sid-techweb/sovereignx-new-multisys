from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
from app.services.sovereignty import SovereigntyMonitor

router = APIRouter(prefix="/api/sovereignty", tags=["sovereignty"])

@router.get("/status")
def get_status():
    monitor = SovereigntyMonitor()
    return monitor.get_summary()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    monitor = SovereigntyMonitor()
    
    # Callback to push new connection events directly to the WebSocket client
    def push_update(entry):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    websocket.send_json({
                        "type": "connection",
                        "entry": entry,
                        "summary": monitor.get_summary()
                    }),
                    loop
                )
        except Exception:
            pass

    monitor.register_subscriber(push_update)
    
    # Send initial state immediately upon connection
    try:
        await websocket.send_json({
            "type": "init",
            "summary": monitor.get_summary()
        })
        
        while True:
            # Keep the socket open, discard incoming client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        monitor.unregister_subscriber(push_update)
