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
            deployment_name = self.deployment_name

            if imgUrl:
                dialogue = self.vllm_chat_response(dialogue, imgUrl, deployment_name)

            stream = self.client.chat.completions.create(
                model=deployment_name,  # 使用 deployment_name
                messages=dialogue,
                stream=True,
                tools=functions
            )

            for chunk in stream:
                if getattr(chunk, "choices", None):
                    yield chunk.choices[0].delta.content, chunk.choices[0].delta.tool_calls
                    logger.bind(tag=TAG).info(
                        f"LLM: {chunk.choices[0].delta.content, chunk.choices[0].delta.tool_calls}")
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

    def vllm_chat_response(self, dialogue, imgUrl, deployment_name):
        domain_mapping = {
            "https://dev-oss.iot-solution.net": "https://sma-hk-test.oss-accelerate.aliyuncs.com",
            "https://test-oss.iot-solution.net": "https://sma-test.oss-accelerate.aliyuncs.com",
            "https://api-oss.iot-solution.net": "https://sma-product.oss-accelerate.aliyuncs.com",
            "https://coding-eu-oss.iot-solution.net": "https://coding-eu.oss-accelerate.aliyuncs.com",
            "https://coding-shenzhen-oss.iot-solution.net": "https://coding-shenzhen.oss-accelerate.aliyuncs.com",
            "https://coding-usa-oss.iot-solution.net": "https://coding-usa.oss-accelerate.aliyuncs.com"
        }

        for old_domain, new_domain in domain_mapping.items():
            if imgUrl.startswith(old_domain):
                imgUrl = imgUrl.replace(old_domain, new_domain, 1)
                break  # 找到就替换，无需再判断后面的

        deployment_name = "gpt4o"

        logger.bind(tag=TAG).info(f"response_with_functions imgUrl: {imgUrl},deployment_name:{deployment_name}")
        logger.bind(tag=TAG).info(f"dialogue: {dialogue}")

        # 找到最后一条 user 消息
        last_user = None
        for i in range(len(dialogue) - 1, -1, -1):
            if dialogue[i].get("role") == "user":
                original_text = dialogue[i].get("content", "")
                if not original_text or not original_text.strip():
                    original_text = "请查看这张图片"
                last_user = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": original_text},
                        {"type": "image_url", "image_url": {"url": imgUrl}}
                    ]
                }
                break

        # 保留所有 assistant.tool_calls + 对应 tool 消息
        valid_tool_messages = []
        valid_tool_ids = set()

        for msg in dialogue:
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                # 自动补 ID
                for i, call in enumerate(msg["tool_calls"]):
                    if not call.get("id"):
                        call["id"] = f"tool_call_{i}"
                    valid_tool_ids.add(call["id"])
                valid_tool_messages.append(msg)
            elif msg.get("role") == "tool" and msg.get("tool_call_id") in valid_tool_ids:
                valid_tool_messages.append(msg)

        # 构建最终 dialogue
        dialogue = valid_tool_messages + ([last_user] if last_user else [])
        return dialogue
