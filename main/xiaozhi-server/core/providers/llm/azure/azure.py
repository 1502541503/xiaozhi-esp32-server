import httpx
from openai import AzureOpenAI  # 改为导入 AzureOpenAI
from openai.types import CompletionUsage
from config.logger import setup_logging
from core.utils.util import check_model_key
from core.providers.llm.base import LLMProviderBase

TAG = __name__
logger = setup_logging()


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.deployment_name = config.get("deployment_name")  # Azure 使用 deployment 名称
        self.api_key = config.get("api_key")
        self.endpoint = config.get("end_point")  # Azure 特定 endpoint
        self.api_version = config.get("api_version", "2025-01-01-preview")  # Azure API 版本
        self.max_tokens = config.get("max_tokens", 300)

        # 移除 base_url/url 处理，使用 endpoint
        timeout = config.get("timeout", 300)
        self.timeout = int(timeout) if timeout else 300

        param_defaults = {
            "max_tokens": (500, int),
            "temperature": (0.7, lambda x: round(float(x), 1)),
            "top_p": (1.0, lambda x: round(float(x), 1)),
            "frequency_penalty": (0, lambda x: round(float(x), 1)),
        }

        for param, (default, converter) in param_defaults.items():
            value = config.get(param)
            try:
                setattr(
                    self,
                    param,
                    converter(value) if value not in (None, "") else default,
                )
            except (ValueError, TypeError):
                setattr(self, param, default)

        check_model_key("LLM", self.api_key)

        # 使用 AzureOpenAI 客户端
        self.client = AzureOpenAI(
            azure_endpoint=self.endpoint,
            azure_deployment=self.deployment_name,
            api_version=self.api_version,
            api_key=self.api_key,
            timeout=httpx.Timeout(self.timeout)
        )

    def response(self, session_id, dialogue, **kwargs):
        try:
            responses = self.client.chat.completions.create(
                model=self.deployment_name,  # 使用 deployment_name
                messages=dialogue,
                stream=True,
                max_tokens=kwargs.get("max_tokens", self.max_tokens),
            )

            is_active = True
            for chunk in responses:
                try:
                    delta = (
                        chunk.choices[0].delta
                        if getattr(chunk, "choices", None)
                        else None
                    )
                    content = delta.content if hasattr(delta, "content") else ""
                    logger.bind(tag=TAG).info(f"LLM: {content}")
                except IndexError:
                    content = ""
                if content:
                    if "<think>" in content:
                        is_active = False
                        content = content.split("<think>")[0]
                    if "</think>" in content:
                        is_active = True
                        content = content.split("</think>")[-1]
                    if is_active:
                        yield content

        except Exception as e:
            logger.bind(tag=TAG).error(f"Error in response generation: {e}")

    def response_with_functions(self, session_id, dialogue, functions=None, imgUrl=None):
        try:
            stream = self.client.chat.completions.create(
                model=self.deployment_name,  # 使用 deployment_name
                messages=dialogue,
                stream=True,
                tools=functions
            )

            for chunk in stream:
                if getattr(chunk, "choices", None):
                    yield chunk.choices[0].delta.content, chunk.choices[0].delta.tool_calls
                    logger.bind(tag=TAG).info(f"LLM: {chunk.choices[0].delta.content, chunk.choices[0].delta.tool_calls}")
                elif isinstance(getattr(chunk, "usage", None), CompletionUsage):
                    usage_info = getattr(chunk, "usage", None)
                    logger.bind(tag=TAG).info(
                        f"Token 消耗：输入 {getattr(usage_info, 'prompt_tokens', '未知')}，"
                        f"输出 {getattr(usage_info, 'completion_tokens', '未知')}，"
                        f"共计 {getattr(usage_info, 'total_tokens', '未知')}"
                    )

        except Exception as e:
            logger.bind(tag=TAG).error(f"Error in function call streaming: {e}")
            yield f"【OpenAI服务响应异常: {e}】", None
