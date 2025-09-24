# ---------------------------------------------------------------------
# 真实 UDP 适配（跨平台）：asyncio.create_datagram_endpoint 版本
# ---------------------------------------------------------------------
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Dict, Any, Tuple, Callable

logger = logging.getLogger("driver.sdk")
if not logger.handlers:
    _h = logging.StreamHandler()
    _fmt = logging.Formatter(
        fmt="ts=%(asctime)s module=driver.sdk level=%(levelname)s event=%(message)s task_id=%(task_id)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _h.setFormatter(_fmt)
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

RespCallback = Callable[[str, int, Dict[str, Any] | None], None]


class _UDPProtocol(asyncio.DatagramProtocol):
    """收包协议：把 Tello 返回的文本扔进队列。"""
    def __init__(self, rx_queue: asyncio.Queue[str]) -> None:
        self.rx_queue = rx_queue
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        msg = data.decode("utf-8", errors="ignore").strip()
        # Tello 回复可能是 'ok' / 'error' / 数字（如电量）
        try:
            self.rx_queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass  # 不阻塞

    def error_received(self, exc: Exception) -> None:
        logger.error(f"udp_error:{exc}", extra={"task_id": "-"})

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc:
            logger.error(f"udp_lost:{exc}", extra={"task_id": "-"})


class _TelloDriver:
    """
    Tello 真实 UDP 驱动（控制端口 8889）
      connect(): 绑定本地端口 → 进入 SDK 模式（发送 'command' 等 'ok'）
      send_cmd(): 发送纯文本命令（如 'takeoff' / 'land'）
      heartbeat(): 用 'battery?' 作为心跳
    """
    def __init__(self, local_port: int = 9000) -> None:
        self.connected = False
        self._resp_cb: Optional[RespCallback] = None
        self._rx_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=64)
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._protocol: Optional[_UDPProtocol] = None
        self._remote: Tuple[str, int] = ("192.168.10.1", 8889)
        self._local_port = local_port
        self._last_task_id = "-"
        self.last_battery: int | None = None

    def set_resp_callback(self, cb: RespCallback) -> int:
        self._resp_cb = cb
        return 0

    def _is_ok_or_error(msg: str) -> bool:
        m = msg.lower()
        return m == "ok" or m == "error"

    def _is_digits(msg: str) -> bool:
        return msg.isdigit()

    async def _ensure_socket(self) -> None:
        """创建 UDP 套接字并启动接收协议。"""
        if self._transport is not None:
            return
        loop = asyncio.get_running_loop()
        self._protocol = _UDPProtocol(self._rx_queue)
        # 绑定本地端口（0.0.0.0:local_port）
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: self._protocol, local_addr=("0.0.0.0", self._local_port)
        )
        self._transport = transport  # type: ignore[assignment]
        self._protocol = protocol    # type: ignore[assignment]
        logger.info("connect_real_udp_bind", extra={"task_id": "-"})

    def _drain_rx_queue(self) -> None:
        """非阻塞清空接收队列，避免上一次命令的残留影响本次判断。"""
        try:
            while True:
                self._rx_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

    async def _send_and_wait(
        self,
        text: str,
        timeout: float,
        accept_pred=None,
    ) -> str:
        """
        发送命令并等待匹配的应答：
          - 先清空队列，避免旧帧干扰
          - 接收直到超时或谓词匹配（默认：任何非空文本即接受）
        """
        if self._transport is None:
            return ""

        # 先清空旧消息
        self._drain_rx_queue()

        # 发送
        self._transport.sendto(text.encode("utf-8"), self._remote)

        # 谓词：默认接受任何非空字符串
        def _any(s: str) -> bool:
            return bool(s)

        pred = accept_pred or _any

        # 等待匹配
        try:
            while True:
                resp = await asyncio.wait_for(self._rx_queue.get(), timeout=timeout)
                # 某些帧可能是二进制残包被 decode 出奇怪字符，统一 strip 后再判断
                if isinstance(resp, str) and pred(resp):
                    return resp
        except asyncio.TimeoutError:
            return ""

    async def connect(self, ip: str, port: int) -> int:
        if ip:
            self._remote = (ip, port or 8889)
        await self._ensure_socket()

        # 进入 SDK 模式：仅接受 ok/error 作为有效应答
        def _is_ok_or_error(s: str) -> bool:
            t = s.lower()
            return t == "ok" or t == "error"

        resp = await self._send_and_wait("command", timeout=2.0, accept_pred=_is_ok_or_error)
        if resp.lower() == "ok":
            self.connected = True
            logger.info("sdk_mode_ok", extra={"task_id": "-"})
            return 0
        logger.error(f"sdk_mode_fail:{resp!r}", extra={"task_id": "-"})
        return -1

    # ---- 替换 _TelloDriver 内的 send_cmd() ----
    async def send_cmd(self, cmd: str, json_param: Dict[str, Any], timeout_ms: int) -> None:
        self._last_task_id = str(json_param.get("task_id", "-"))

        if not self.connected or self._transport is None:
            logger.error("send_cmd_not_connected", extra={"task_id": self._last_task_id})
            # 尝试自愈一次
            _ = await self.reconnect_if_needed()
            if not self.connected:
                if self._resp_cb:
                    self._resp_cb(cmd, 0, {"error": "not_connected", "task_id": self._last_task_id})
                return

        text = cmd.strip()
        logger.info("send_cmd", extra={"task_id": self._last_task_id})

        # 仅接受 ok/error 作为有效应答
        def _is_ok_or_error(s: str) -> bool:
            t = s.lower()
            return t == "ok" or t == "error"

        resp = await self._send_and_wait(text, timeout=timeout_ms / 1000.0, accept_pred=_is_ok_or_error)

        if not resp:
            # === 超时：可能回包丢失，但命令已在机上执行（典型：takeoff 成功但未回 ok）===
            # 仅对关键动作启用“假定成功”，避免误报（可按需扩展）
            assumable_cmds = {"takeoff", "land"}
            if cmd.lower() in assumable_cmds:
                logger.warning("ack_timeout_but_may_executed", extra={"task_id": self._last_task_id})
                if self._resp_cb:
                    self._resp_cb(cmd, 1, {
                        "ack": True,
                        "assumed": True,  # 告诉上层：这是“假定成功”
                        "task_id": self._last_task_id
                    })
                return
            # 其他命令仍按超时失败处理
            logger.error("ack_timeout", extra={"task_id": self._last_task_id})
            if self._resp_cb:
                self._resp_cb(cmd, 0, {"error": "timeout", "task_id": self._last_task_id})
            return

        if resp.lower() == "ok":
            if self._resp_cb:
                self._resp_cb(cmd, 1, {"ack": True, "task_id": self._last_task_id})
            logger.info("recv_ack", extra={"task_id": self._last_task_id})
        else:
            if self._resp_cb:
                self._resp_cb(cmd, 0, {"error": resp, "task_id": self._last_task_id})
            logger.warning(f"ack_fail:{resp}", extra={"task_id": self._last_task_id})

    async def heartbeat(self) -> int:
        if self._transport is None:
            return -1

        def _is_digits(s: str) -> bool:
            return s.isdigit()

        resp = await self._send_and_wait("battery?", timeout=1.0, accept_pred=_is_digits)
        if resp.isdigit():
            self.last_battery = int(resp)  # ← 缓存
            logger.info("heartbeat_ok", extra={"task_id": "-"})
            return 0
        logger.warning(f"heartbeat_bad:{resp!r}", extra={"task_id": "-"})
        return -1


# ===================== 模块级单例 & 对外 API =====================

# 单例驱动（保持整个进程只用一个 UDP transport）
_driver = _TelloDriver(local_port=9000)

def configure(remote_ip: str = "192.168.10.1", remote_port: int = 8889, local_port: int = 9000) -> None:
    """
    修改远端/本地端口配置（需在 connect() 之前调用）。
    """
    _driver._remote = (remote_ip, remote_port)
    _driver._local_port = local_port

def set_resp_callback(cb: RespCallback) -> int:
    """
    注册命令应答回调：
        cb(cmd: str, ok: int, payload: dict | None) -> None
    其中 payload 推荐包含 task_id，便于上层关联。
    """
    return _driver.set_resp_callback(cb)

async def connect(ip: str, port: int) -> int:
    """
    连接并进入 SDK 模式。
    返回 0 表示 ok，非 0 表示失败（例如未收到 `ok`）。
    """
    if ip:
        _driver._remote = (ip, port or 8889)
    return await _driver.connect(ip=_driver._remote[0], port=_driver._remote[1])

async def send_cmd(cmd: str, json_param: Dict[str, Any], timeout_ms: int) -> None:
    """
    发送控制命令；在 timeout_ms 内等应答并通过回调上报。
    """
    await _driver.send_cmd(cmd, json_param, timeout_ms)

async def heartbeat() -> int:
    """
    心跳：当前用 `battery?` 查询判断联通性。
    返回 0=OK，非 0=失败。
    """
    return await _driver.heartbeat()

async def reconnect_if_needed() -> int:
    """
    若未处于 SDK 模式，尝试重新 `command`；返回 0=恢复成功。
    """
    return await _driver.reconnect_if_needed()

async def close() -> None:
    """
    资源释放（可选）：关闭 UDP Transport。
    """
    if _driver._transport is not None:
        _driver._transport.close()
        _driver._transport = None
        _driver._protocol = None
        _driver.connected = False
        logger.info("udp_closed", extra={"task_id": "-"})

def get_last_battery() -> int | None:
    """返回最近一次 heartbeat() 解析到的电量（百分比），可能为 None。"""
    return _driver.last_battery


