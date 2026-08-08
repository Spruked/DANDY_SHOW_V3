import asyncio
import base64
import hashlib
import json
import os
from typing import Any, Callable, Dict
from uuid import uuid4

import websockets

from ...core.settings import load_project_config


class OBSError(Exception):
    pass


class OBSConnectionError(OBSError):
    pass


class OBSRequestError(OBSError):
    pass


class OBSClient:
    def __init__(self, host: str, port: int, password: str = "", timeout_seconds: float = 2.5):
        self.host = host
        self.port = int(port)
        self.password = password or ""
        self.timeout_seconds = float(timeout_seconds)

    @classmethod
    def from_runtime_config(cls) -> "OBSClient":
        config = load_project_config().get("obs", {})
        host = str(config.get("host") or os.getenv("OBS_HOST") or "127.0.0.1")
        port = int(config.get("port") or os.getenv("OBS_PORT") or 4455)
        password = str(config.get("password") or os.getenv("OBS_PASSWORD") or "")
        timeout_seconds = float(config.get("timeout_seconds") or os.getenv("OBS_TIMEOUT_SECONDS") or 2.5)
        return cls(host=host, port=port, password=password, timeout_seconds=timeout_seconds)

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    async def status(self) -> Dict[str, Any]:
        async def _run(ws) -> Dict[str, Any]:
            version = await self._request(ws, "GetVersion")
            stream = await self._request(ws, "GetStreamStatus")
            record = await self._request(ws, "GetRecordStatus")
            scene = await self._request(ws, "GetCurrentProgramScene")
            return {
                "connected": True,
                "obs_version": version.get("obsVersion"),
                "obs_websocket_version": version.get("obsWebSocketVersion"),
                "scene_name": scene.get("currentProgramSceneName") or "",
                "streaming": bool(stream.get("outputActive")),
                "recording": bool(record.get("outputActive")),
                "stream_timecode": stream.get("outputTimecode") or "00:00:00.000",
                "record_timecode": record.get("outputTimecode") or "00:00:00.000",
                "stream_duration_seconds": self._timecode_to_seconds(stream.get("outputTimecode") or ""),
                "record_duration_seconds": self._timecode_to_seconds(record.get("outputTimecode") or ""),
            }

        return await self._with_connection(_run)

    async def scenes(self) -> Dict[str, Any]:
        async def _run(ws) -> Dict[str, Any]:
            data = await self._request(ws, "GetSceneList")
            scenes = [item.get("sceneName") for item in data.get("scenes", []) if item.get("sceneName")]
            return {
                "connected": True,
                "active_scene": data.get("currentProgramSceneName") or "",
                "scenes": scenes,
            }

        return await self._with_connection(_run)

    async def set_scene(self, scene_name: str) -> Dict[str, Any]:
        scene_name = str(scene_name or "").strip()
        if not scene_name:
            raise OBSRequestError("scene_name is required")

        async def _run(ws) -> Dict[str, Any]:
            await self._request(ws, "SetCurrentProgramScene", {"sceneName": scene_name})
            data = await self._request(ws, "GetCurrentProgramScene")
            return {"connected": True, "active_scene": data.get("currentProgramSceneName") or scene_name}

        return await self._with_connection(_run)

    async def toggle_stream(self) -> Dict[str, Any]:
        async def _run(ws) -> Dict[str, Any]:
            current = await self._request(ws, "GetStreamStatus")
            if current.get("outputActive"):
                await self._request(ws, "StopStream")
            else:
                await self._request(ws, "StartStream")
            latest = await self._request(ws, "GetStreamStatus")
            return {
                "connected": True,
                "streaming": bool(latest.get("outputActive")),
                "stream_timecode": latest.get("outputTimecode") or "00:00:00.000",
                "stream_duration_seconds": self._timecode_to_seconds(latest.get("outputTimecode") or ""),
            }

        return await self._with_connection(_run)

    async def toggle_record(self) -> Dict[str, Any]:
        async def _run(ws) -> Dict[str, Any]:
            current = await self._request(ws, "GetRecordStatus")
            if current.get("outputActive"):
                await self._request(ws, "StopRecord")
            else:
                await self._request(ws, "StartRecord")
            latest = await self._request(ws, "GetRecordStatus")
            return {
                "connected": True,
                "recording": bool(latest.get("outputActive")),
                "record_timecode": latest.get("outputTimecode") or "00:00:00.000",
                "record_duration_seconds": self._timecode_to_seconds(latest.get("outputTimecode") or ""),
            }

        return await self._with_connection(_run)

    async def _with_connection(self, handler: Callable[[Any], Any]) -> Dict[str, Any]:
        try:
            async with websockets.connect(
                self.url,
                open_timeout=self.timeout_seconds,
                close_timeout=self.timeout_seconds,
                max_size=2_000_000,
                ping_interval=20,
                ping_timeout=20,
            ) as ws:
                await self._identify(ws)
                return await handler(ws)
        except OBSError:
            raise
        except Exception as exc:
            raise OBSConnectionError(f"Could not connect to OBS WebSocket at {self.url}: {exc}") from exc

    async def _identify(self, ws: Any) -> None:
        hello = await self._recv_json(ws)
        if hello.get("op") != 0:
            raise OBSConnectionError("Unexpected OBS handshake response")

        hello_data = hello.get("d", {})
        identify_data: Dict[str, Any] = {"rpcVersion": hello_data.get("rpcVersion", 1)}

        auth = hello_data.get("authentication") or {}
        if auth:
            if not self.password:
                raise OBSConnectionError("OBS requires authentication but no OBS password is configured")
            salt = str(auth.get("salt") or "")
            challenge = str(auth.get("challenge") or "")
            if not salt or not challenge:
                raise OBSConnectionError("OBS authentication challenge was incomplete")
            secret = base64.b64encode(hashlib.sha256(f"{self.password}{salt}".encode("utf-8")).digest()).decode("utf-8")
            response = base64.b64encode(hashlib.sha256(f"{secret}{challenge}".encode("utf-8")).digest()).decode("utf-8")
            identify_data["authentication"] = response

        await self._send_json(ws, {"op": 1, "d": identify_data})

        # Ignore async events until the identify ACK arrives.
        for _ in range(20):
            message = await self._recv_json(ws)
            op = message.get("op")
            if op == 2:
                return
            if op == 5:
                continue
            raise OBSConnectionError("OBS identify failed")
        raise OBSConnectionError("OBS identify timeout")

    async def _request(self, ws: Any, request_type: str, request_data: Dict[str, Any] | None = None) -> Dict[str, Any]:
        request_id = uuid4().hex
        await self._send_json(
            ws,
            {
                "op": 6,
                "d": {
                    "requestType": request_type,
                    "requestId": request_id,
                    "requestData": request_data or {},
                },
            },
        )

        for _ in range(50):
            message = await self._recv_json(ws)
            if message.get("op") != 7:
                continue
            data = message.get("d", {})
            if data.get("requestId") != request_id:
                continue
            status = data.get("requestStatus", {})
            if not status.get("result"):
                code = status.get("code", "unknown")
                comment = status.get("comment", "request failed")
                raise OBSRequestError(f"{request_type} failed ({code}): {comment}")
            return data.get("responseData", {})
        raise OBSRequestError(f"{request_type} timed out")

    async def _recv_json(self, ws: Any) -> Dict[str, Any]:
        raw = await asyncio.wait_for(ws.recv(), timeout=self.timeout_seconds)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if not isinstance(raw, str):
            raise OBSConnectionError("Received non-text OBS payload")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OBSConnectionError("Received invalid OBS JSON payload") from exc

    async def _send_json(self, ws: Any, payload: Dict[str, Any]) -> None:
        await asyncio.wait_for(ws.send(json.dumps(payload)), timeout=self.timeout_seconds)

    @staticmethod
    def _timecode_to_seconds(timecode: str) -> int:
        if not timecode or ":" not in timecode:
            return 0
        try:
            hours, minutes, sec_fraction = str(timecode).split(":")
            seconds = float(sec_fraction)
            total = (int(hours) * 3600) + (int(minutes) * 60) + seconds
            return max(0, int(total))
        except Exception:
            return 0
