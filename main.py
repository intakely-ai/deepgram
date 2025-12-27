import asyncio
import base64
import json
import os
import signal
from http import HTTPStatus

from dotenv import load_dotenv
load_dotenv()  # ← load env BEFORE importing anything that reads env

import websockets
from websockets import exceptions as ws_exc
from websockets.asyncio.server import serve  # explicit for >=13

from law_functions import FUNCTION_MAP

WS_HOST = os.getenv("WS_HOST", "0.0.0.0")
WS_PORT = int(os.getenv("WS_PORT", "5000"))
WS_PATH = os.getenv("WS_PATH", "/twilio")   # <— keep in sync with TwiML

DEEPGRAM_WSS = "wss://agent.deepgram.com/v1/agent/converse"

# Optional: path to 8kHz μ-law audio to play on shutdown (20ms framing handled)
GOODBYE_ULAW_PATH = os.getenv("GOODBYE_ULAW_PATH", "").strip()

# Global stop signal for graceful shutdown
STOP_EVENT = asyncio.Event()


def sts_connect():
    api_key = os.getenv("DEEPGRAM_API_KEY")
    if not api_key:
        raise Exception("DEEPGRAM_API_KEY not found")
    return websockets.connect(
        DEEPGRAM_WSS,
        subprotocols=["token", api_key],
        max_size=None,
        ping_interval=20,
        ping_timeout=20,
    )


def load_config():
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


async def handle_barge_in(decoded, twilio_ws, streamsid):
    if decoded.get("type") == "UserStartedSpeaking":
        await twilio_ws.send(json.dumps({"event": "clear", "streamSid": streamsid}))


def execute_function_call(func_name, arguments):
    if func_name in FUNCTION_MAP:
        result = FUNCTION_MAP[func_name](**arguments)
        print(f"[Function] {func_name} -> {result}")
        return result
    result = {"error": f"Unknown function: {func_name}"}
    print(f"[Function] {result}")
    return result


def create_function_call_response(func_id, func_name, result):
    return {
        "type": "FunctionCallResponse",
        "id": func_id,
        "name": func_name,
        "content": json.dumps(result),
    }


async def handle_function_call_request(decoded, sts_ws):
    try:
        for function_call in decoded.get("functions", []):
            func_name = function_call.get("name")
            func_id = function_call.get("id")
            arguments = json.loads(function_call.get("arguments", "{}") or "{}")
            print(f"[FunctionCallRequest] {func_name} (id={func_id}) args={arguments}")
            result = execute_function_call(func_name, arguments)
            await sts_ws.send(json.dumps(create_function_call_response(func_id, func_name, result)))
    except Exception as e:
        print(f"[Function ERROR] {e}")
        fallback = create_function_call_response(
            function_call.get("id", "unknown") if "function_call" in locals() else "unknown",
            function_call.get("name", "unknown") if "function_call" in locals() else "unknown",
            {"error": f"Function call failed with: {str(e)}"},
        )
        try:
            await sts_ws.send(json.dumps(fallback))
        except Exception:
            pass


async def handle_text_message(decoded, twilio_ws, sts_ws, streamsid):
    await handle_barge_in(decoded, twilio_ws, streamsid)
    if decoded.get("type") == "FunctionCallRequest":
        await handle_function_call_request(decoded, sts_ws)


async def sts_sender(sts_ws, audio_queue):
    print("[sts_sender] started")
    try:
        while True:
            chunk = await audio_queue.get()
            await sts_ws.send(chunk)
    except asyncio.CancelledError:
        print("[sts_sender] cancelled")
        raise
    except (ws_exc.ConnectionClosedOK, ws_exc.ConnectionClosedError) as e:
        print(f"[sts_sender] connection closed: {e}")


async def sts_receiver(sts_ws, twilio_ws, streamsid_queue):
    print("[sts_receiver] started")
    streamsid = await streamsid_queue.get()
    print(f"[sts_receiver] using streamSid={streamsid}")
    try:
        async for message in sts_ws:
            if isinstance(message, str):
                print(f"[Deepgram TEXT] {message}")
                try:
                    decoded = json.loads(message)
                except json.JSONDecodeError:
                    continue
                await handle_text_message(decoded, twilio_ws, sts_ws, streamsid)
            else:
                media_message = {
                    "event": "media",
                    "streamSid": streamsid,
                    "media": {"payload": base64.b64encode(message).decode("ascii")},
                }
                await twilio_ws.send(json.dumps(media_message))
    except asyncio.CancelledError:
        print("[sts_receiver] cancelled")
        raise
    except (ws_exc.ConnectionClosedOK, ws_exc.ConnectionClosedError) as e:
        print(f"[sts_receiver] connection closed: {e}")


async def twilio_receiver(twilio_ws, audio_queue, streamsid_queue):
    print("[twilio_receiver] started")
    BUFFER_SIZE = 20 * 160  # 20ms @ 8kHz μ-law (160 bytes per 20ms * 20 = 3200B chunk to STS)
    inbuffer = bytearray()
    try:
        async for message in twilio_ws:
            try:
                data = json.loads(message)
            except Exception as e:
                print(f"[twilio_receiver] JSON error: {e}")
                continue

            event = data.get("event")
            if event == "start":
                streamsid = data.get("start", {}).get("streamSid")
                print(f"[twilio_receiver] start, streamSid={streamsid}")
                if streamsid:
                    streamsid_queue.put_nowait(streamsid)
            elif event == "media":
                media = data.get("media", {})
                if media.get("track") == "inbound" and media.get("payload"):
                    inbuffer.extend(base64.b64decode(media["payload"]))
            elif event == "stop":
                print("[twilio_receiver] stop received")
                break

            while len(inbuffer) >= BUFFER_SIZE:
                chunk = inbuffer[:BUFFER_SIZE]
                audio_queue.put_nowait(chunk)
                del inbuffer[:BUFFER_SIZE]
    except asyncio.CancelledError:
        print("[twilio_receiver] cancelled")
        raise
    except (ws_exc.ConnectionClosedOK, ws_exc.ConnectionClosedError) as e:
        print(f"[twilio_receiver] connection closed: {e}")


async def try_send_goodbye(twilio_ws, streamsid):
    """
    If GOODBYE_ULAW_PATH is set to an 8kHz μ-law file, play it out to Twilio in 20ms frames.
    Otherwise, do nothing (we won't synthesize speech here).
    """
    path = GOODBYE_ULAW_PATH
    if not path:
        return
    try:
        # Support .wav (μ-law) or raw μ-law; if .wav, skip 44-byte header.
        with open(path, "rb") as f:
            data = f.read()
        if path.lower().endswith(".wav") and len(data) > 44:
            data = data[44:]  # naive WAV header skip; works for PCM8 μ-law mono
        FRAME_BYTES = 160  # 20ms at 8kHz μ-law
        for i in range(0, len(data), FRAME_BYTES):
            frame = data[i:i+FRAME_BYTES]
            if not frame:
                break
            media_message = {
                "event": "media",
                "streamSid": streamsid,
                "media": {"payload": base64.b64encode(frame).decode("ascii")},
            }
            await twilio_ws.send(json.dumps(media_message))
            await asyncio.sleep(0.020)  # pace at 20ms per frame
        # then ask Twilio to stop
        await twilio_ws.send(json.dumps({"event": "mark", "streamSid": streamsid, "mark": {"name": "server_goodbye_done"}}))
    except Exception as e:
        print(f"[goodbye] failed to play audio: {e}")


async def twilio_handler(twilio_ws):
    audio_queue = asyncio.Queue()
    streamsid_queue = asyncio.Queue()
    sts_ws = None
    try:
        async with sts_connect() as sts_ws:
            await sts_ws.send(json.dumps(load_config()))
            tasks = [
                asyncio.create_task(sts_sender(sts_ws, audio_queue)),
                asyncio.create_task(sts_receiver(sts_ws, twilio_ws, streamsid_queue)),
                asyncio.create_task(twilio_receiver(twilio_ws, audio_queue, streamsid_queue)),
            ]
            try:
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                for t in done:
                    if exc := t.exception():
                        raise exc
            finally:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                # If we are stopping the whole server, try to play a short goodbye clip (optional)
                if STOP_EVENT.is_set():
                    # Get a streamSid if available
                    streamsid = None
                    try:
                        streamsid = streamsid_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    if streamsid:
                        await try_send_goodbye(twilio_ws, streamsid)
                await twilio_ws.close()
    except asyncio.CancelledError:
        print("[twilio_handler] cancelled")
        try:
            await twilio_ws.close()
        except Exception:
            pass
        raise
    except (ws_exc.ConnectionClosedOK, ws_exc.ConnectionClosedError) as e:
        print(f"[twilio_handler] ws closed: {e}")


# ---- websockets ≥13 style process_request: use connection.respond(...) ----
def process_request(connection, request):
    """
    Health check on "/" and only allow WS upgrade on WS_PATH.
    """
    if request.path == "/":
        return connection.respond(HTTPStatus.OK, "OK\n")
    if request.path != WS_PATH:
        return connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")
    return None  # proceed with WS handshake for WS_PATH


async def main():
    # Wire signals to STOP_EVENT so Ctrl+C / SIGTERM shuts down cleanly
    loop = asyncio.get_running_loop()
    try:
        loop.add_signal_handler(signal.SIGINT, STOP_EVENT.set)
        loop.add_signal_handler(signal.SIGTERM, STOP_EVENT.set)
    except NotImplementedError:
        # Windows may not support signal handlers in asyncio; fallback to KeyboardInterrupt below
        pass

    async with serve(
        twilio_handler,
        WS_HOST,
        WS_PORT,
        process_request=process_request,
        max_size=None,
        ping_interval=20,
        ping_timeout=20,
    ):
        print(f"[server] Started on ws://{WS_HOST}:{WS_PORT} (expose as wss://...{WS_PATH}) — press Ctrl+C to stop")
        try:
            await STOP_EVENT.wait()  # wait until a stop signal arrives
        except asyncio.CancelledError:
            pass
        print("[server] Shutdown requested. Closing gracefully...")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # On Windows, asyncio signal handler may not fire; this keeps it clean.
        print("\n[server] Stopped by user. Goodbye.")
