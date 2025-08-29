from typing import Dict, Any, Optional
import json
from dataclasses import dataclass
from enum import Enum

@dataclass
class ErrorInfo:
    """错误信息数据类"""
    code: str
    msg: str

class ErrorCode(Enum):
    """异常代码枚举"""
    """
    !!! 注意：
    code小于5000统一为运行时异常，客户端如果断开连接会尝试重新连接
    code大于5000统一为阻断性异常，客户端会断开连接不再重连
    """
    # ASR相关错误
    ASR_MANAGER_ERROR = ErrorInfo("4001", "处理ASR异常")
    ASR_NO_VOICE_ERROR = ErrorInfo("4002", "音频无声音，并后续无音频推送")

    # LLM相关错误
    LLM_MANAGER_ERROR = ErrorInfo("4003", "处理LLM异常")

    # TTS相关错误
    TTS_MANAGER_ERROR = ErrorInfo("4006", "语音合成异常")

    # 音频相关错误
    VOICE_DECODE_ERROR = ErrorInfo("4004", "音频解码过程发生异常")
    VOICE_DECODE_PK_ERROR = ErrorInfo("4005", "音频解码包异常")

    # 授权相关错误
    AUTH_ERROR = ErrorInfo("5001", "授权异常")
    AUTH_MAC_ERROR = ErrorInfo("5002", "mac授权异常")
    AUTH_QUERY_ERROR = ErrorInfo("5003", "mac授权查询异常")
    AUTH_TOKEN_ERROR = ErrorInfo("5004", "TOKEN异常")
    # 可以继续添加其他错误码


@dataclass
class ErrorMessage:
    """异常消息数据类"""
    code: str
    msg: str
    details: Optional[Dict[str, Any]] = None


class WebSocketErrorManager:
    """WebSocket异常管理器"""

    @staticmethod
    def create_error_response(
            error_code: ErrorCode,
            details: Optional[Dict[str, Any]] = None
    ) -> str:
        """创建错误响应JSON字符串

        Args:
            error_code: 错误代码枚举
            details: 额外的错误详情

        Returns:
            JSON格式的错误响应字符串
        """
        response = {
            "type": "server",
            "code": error_code.value.code,
            "msg": error_code.value.msg
        }

        # 添加额外详情（如果有）
        if details:
            response["details"] = details

        return json.dumps(response)
