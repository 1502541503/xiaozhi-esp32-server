import asyncio
import json
import time

import websockets

try:
    from websockets.http import Headers, Response
except ImportError:
    from websockets.legacy.http import Headers  # 旧版本没有 Response

    Response = None
try:
    from websockets.exceptions import AbortHandshake
except ImportError:
    from websockets.legacy.exceptions import AbortHandshake

from config.logger import setup_logging
from core.connection import ConnectionHandler
from config.config_loader import get_config_from_api
from core.utils.modules_initialize import initialize_modules
from core.utils.util import check_vad_update, check_asr_update
from urllib.parse import urlparse, parse_qs

import logging

TAG = __name__

connected = set()


class WebSocketServer:
    def __init__(self, config: dict):
        self.config = config
        self.logger = setup_logging()

        # 配置日志级别为INFO，便于生产环境监控
        logging.getLogger('websockets.server').setLevel(logging.INFO)

        self.config_lock = asyncio.Lock()

        # 稳定性配置
        conn_config = self.config.get("conn", {})
        self.max_connections = conn_config.get("max_connections", 1000)
        self.connection_timeout = conn_config.get("connection_timeout", 300)
        self.heartbeat_interval = conn_config.get("heartbeat_interval", 30)
        self.max_message_size = conn_config.get("max_message_size", 1048576)

        # 连接统计
        self.peak_connections = 0
        self.total_connections = 0
        self.connection_stats_interval = 60  # 统计间隔(秒)

        self.logger.bind(tag=TAG).info(
            f"服务器稳定性配置: 最大连接数={self.max_connections}, 连接超时={self.connection_timeout}秒, 心跳间隔={self.heartbeat_interval}秒")
        modules = initialize_modules(
            self.logger,
            self.config,
            "VAD" in self.config["selected_module"],
            "ASR" in self.config["selected_module"],
            "LLM" in self.config["selected_module"],
            False,
            "Memory" in self.config["selected_module"],
            "Intent" in self.config["selected_module"],
        )
        self._vad = modules["vad"] if "vad" in modules else None
        self._asr = modules["asr"] if "asr" in modules else None
        self._llm = modules["llm"] if "llm" in modules else None
        self._intent = modules["intent"] if "intent" in modules else None
        self._memory = modules["memory"] if "memory" in modules else None

        self.active_connections = set()

    async def start(self):
        server_config = self.config["server"]
        host = server_config.get("ip", "0.0.0.0")
        port = int(server_config.get("port", 8000))

        # 启动连接统计任务
        stats_task = asyncio.create_task(self._log_connection_stats())

        # 应用稳定性配置
        async with websockets.serve(
                handler=self._handle_connection,
                host=host,
                port=port,
                process_request=self._http_response,
        ):
            self.logger.bind(tag=TAG).info(f"WebSocket服务器启动成功，监听端口 {port}，最大连接数 {self.max_connections}")
            try:
                await asyncio.Future()
            finally:
                stats_task.cancel()  # 取消统计任务
                try:
                    await stats_task
                except asyncio.CancelledError:
                    pass
                self.logger.bind(tag=TAG).info(
                    f"WebSocket服务器已关闭。累计连接数: {self.total_connections}, 峰值连接数: {self.peak_connections}")

    async def _handle_connection(self, websocket):
        # 检查当前连接数是否超过最大连接数
        if len(connected) >= self.max_connections:
            await websocket.close(code=5005, reason="Too many connections")
            return

        connected.add(websocket)

        """处理新连接，每次创建独立的ConnectionHandler"""
        # 创建ConnectionHandler时传入当前server实例
        handler = ConnectionHandler(
            self.config,
            self._vad,
            self._asr,
            self._llm,
            self._memory,
            self._intent,
            self,  # 传入server实例
        )
        self.active_connections.add(handler)
        self.total_connections += 1
        current_connections = len(self.active_connections)

        # 更新峰值连接数
        if current_connections > self.peak_connections:
            self.peak_connections = current_connections
            self.logger.bind(tag=TAG).info(f"连接数达到新峰值: {self.peak_connections}")

        # 当连接数接近上限时发出警告
        if current_connections > self.max_connections * 0.8:
            self.logger.bind(tag=TAG).warning(
                f"连接数即将达到上限: {current_connections}/{self.max_connections} ({current_connections / self.max_connections * 100:.1f}%)")

        self.logger.bind(tag=TAG).info(
            f"新连接建立，当前活跃连接数: {current_connections}, 累计连接数: {self.total_connections}")

        # 设置连接超时任务
        timeout_task = asyncio.create_task(self._connection_timeout(websocket))
        try:
            await handler.handle_connection(websocket)
        except websockets.exceptions.ConnectionClosedError as e:
            self.logger.bind(tag=TAG).warning(f"连接已关闭: {e}")
        except websockets.exceptions.ConnectionClosedOK:
            self.logger.bind(tag=TAG).info("连接正常关闭")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"连接处理异常: {str(e)}")
        finally:
            # 取消超时任务
            timeout_task.cancel()
            try:
                await timeout_task
            except asyncio.CancelledError:
                pass
            self.active_connections.discard(handler)
            current_connections = len(self.active_connections)
            self.logger.bind(tag=TAG).info(f"连接已释放，当前活跃连接数: {current_connections}")

    async def _connection_timeout(self, websocket):
        """连接超时处理"""
        try:
            await asyncio.sleep(self.connection_timeout)
            if not websocket.closed:
                self.logger.bind(tag=TAG).warning(f"连接超时 ({self.connection_timeout}秒)，关闭连接")
                await websocket.close(code=1000, reason="Connection timeout")
        except asyncio.CancelledError:
            # 任务被取消时正常退出
            pass

    async def _log_connection_stats(self):
        """定期记录连接统计信息"""
        try:
            while True:
                await asyncio.sleep(self.connection_stats_interval)
                current_connections = len(self.active_connections)
                usage_percent = current_connections / self.max_connections * 100 if self.max_connections > 0 else 0

                self.logger.bind(tag=TAG).info(
                    f"连接统计: 当前活跃连接数={current_connections}, 峰值连接数={self.peak_connections}, "
                    f"累计连接数={self.total_connections}, 连接使用率={usage_percent:.1f}%"
                )
        except asyncio.CancelledError:
            # 任务被取消时正常退出
            pass

    async def _http_response(self, websocket, request_headers):
        # 检查是否为 WebSocket 升级请求
        ble_info_str = request_headers.headers.get("bleinfo") or request_headers.headers.get("BleInfo")

        pid = None

        if ble_info_str:
            try:
                # 解析 JSON 字符串
                ble_info = json.loads(ble_info_str)
                pid = ble_info.get("pid")
                # self.logger.bind(tag=TAG).info(f"解析到 pid: {pid}")
            except Exception as e:
                self.logger.bind(tag=TAG).debug(f"bleinfo 解析失败: {e}")

        if request_headers.headers.get("connection", "").lower() == "upgrade":
            # 如果是 WebSocket 请求，返回 None 允许握手继续
            if pid == "4":
                # self.logger.bind(tag=TAG).warning(f"拒绝连接：pid 非法 ，实际 pid = {pid}")
                raise AbortHandshake(
                    403,
                    Headers([("Content-Type", "text/plain; charset=utf-8")]),
                    b"Forbidden: pid not allowed\n"
                )
            return None
        else:
            # 如果是普通 HTTP 请求，返回 "server is running"
            return websocket.respond(200, "Server is running\n")

    async def update_config(self) -> bool:
        """更新服务器配置并重新初始化组件

        Returns:
            bool: 更新是否成功
        """
        try:
            async with self.config_lock:
                # 重新获取配置
                new_config = get_config_from_api(self.config)
                if new_config is None:
                    self.logger.bind(tag=TAG).error("获取新配置失败")
                    return False
                self.logger.bind(tag=TAG).info(f"获取新配置成功")
                # 检查 VAD 和 ASR 类型是否需要更新
                update_vad = check_vad_update(self.config, new_config)
                update_asr = check_asr_update(self.config, new_config)
                self.logger.bind(tag=TAG).info(
                    f"检查VAD和ASR类型是否需要更新: {update_vad} {update_asr}"
                )
                # 更新配置
                self.config = new_config
                # 重新初始化组件
                modules = initialize_modules(
                    self.logger,
                    new_config,
                    update_vad,
                    update_asr,
                    "LLM" in new_config["selected_module"],
                    False,
                    "Memory" in new_config["selected_module"],
                    "Intent" in new_config["selected_module"],
                )

                # 更新组件实例
                if "vad" in modules:
                    self._vad = modules["vad"]
                if "asr" in modules:
                    self._asr = modules["asr"]
                if "llm" in modules:
                    self._llm = modules["llm"]
                if "intent" in modules:
                    self._intent = modules["intent"]
                if "memory" in modules:
                    self._memory = modules["memory"]
                self.logger.bind(tag=TAG).info(f"更新配置任务执行完毕")
                return True
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"更新服务器配置失败: {str(e)}")
            return False
