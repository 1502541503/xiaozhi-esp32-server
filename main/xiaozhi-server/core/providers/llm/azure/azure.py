import json

import httpx
import asyncio
from openai import AzureOpenAI  # 改为导入 AzureOpenAI
from openai.types import CompletionUsage

from config.logger import setup_logging
from core.ext.WebSocketErrorManager import WebSocketErrorManager, ErrorCode
from core.utils.util import check_model_key
from core.providers.llm.base import LLMProviderBase
from core.handle.functionHandler import FunctionHandler


from plugins_func.register import all_function_registry

TAG = __name__
logger = setup_logging()


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.deployment_name = config.get("deployment_name")  # Azure 使用 deployment 名称
        self.api_key = config.get("api_key")
        self.endpoint = config.get("end_point")  # Azure 特定 endpoint
        self.api_version = config.get("api_version", "2025-01-01-preview")  # Azure API 版本
        self.max_tokens = config.get("max_tokens", 300)
        self.conn = None
        self.headers = None
        self.ws = None
        self.loop = asyncio.get_event_loop()
        self.isAiOnline = None

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

        self.default_vllm_user_msg = "Please describe the image I see, including the scene, main objects, text, and possible branding."
        self.vllm_system_prompt = """
        You are a real-time visual recognition assistant designed for smart glasses.  
        Your task is to capture the user’s surroundings through the glasses’ camera, provide quick, accurate, and vivid scene understanding, and deliver key information through voice.  

        Guidelines:  
        1. Keep responses concise and fluent—3 to 5 sentences, suitable for voice narration.  
        2. Don’t just describe the objects you see—also add a bit of interesting knowledge or background (such as plant habits, drink characteristics, or brand style).  
        3. Use a natural, lively tone, like a thoughtful companion with a touch of encyclopedia knowledge.  

        Example outputs:  
        - "You’re standing in a bright office. On the desk there’s a computer and a coffee cup, a classic work setting."  
        - "There’s a sticky note on the door that says ‘Package picked up,’ probably a little reminder from your roommate."  
        - "In front of you is a 900ml bottle of Oriental Leaf Qinggan Pu’er tea. The Pu’er carries a hint of citrus, often enjoyed as a refreshing drink that cuts through greasiness."  
        - "You’re looking at a blooming peony. With its large, vibrant petals, it’s known as the ‘King of Flowers’ and thrives in full sunlight."  
        """

        # 使用 AzureOpenAI 客户端
        self.client = AzureOpenAI(
            azure_endpoint=self.endpoint,
            azure_deployment=self.deployment_name,
            api_version=self.api_version,
            api_key=self.api_key,
            timeout=httpx.Timeout(self.timeout)
        )

    def build_vllm_system_prompt(self):
        build_vllm_system_prompt_str = f"{self.vllm_system_prompt}"
        if self.headers:
            lang = self.headers.get("accept-language", "zh")
            build_vllm_system_prompt_str += f"\n用户当前使用语言：{lang}  \n请使用用户当前使用语言回答问题。"

        return build_vllm_system_prompt_str

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
        if functions is None:
            functions = []
        try:
            deployment_name = self.deployment_name
            stream_response = None

            if imgUrl:
                deployment_name = "gpt4o"
                dialogue = self.vllm_chat_response(dialogue, imgUrl)
                stream_response = self.client.chat.completions.create(
                    model=deployment_name,
                    messages=dialogue,
                    stream=True
                    # 视觉识别不调用工具方法
                )
            else:

                if self.isAiOnline == True:
                    func = all_function_registry.get("get_web_search").description
                    functions.append(func)

                stream_response = self.client.chat.completions.create(
                    model=deployment_name,  # 使用 deployment_name
                    messages=dialogue,
                    stream=True,
                    tools=functions,
                    temperature=0.7,
                    top_p=0.9
                )

            # 使用封装的流式处理方法
            yield from self.process_stream_with_punctuation(stream_response, session_id)

        except Exception as e:
            logger.bind(tag=TAG).error(f"LLM处理异常: {e}")
            asyncio.run_coroutine_threadsafe(
                self.ws.send(
                    WebSocketErrorManager.create_error_response(ErrorCode.LLM_MANAGER_ERROR, {"e": str(e)})),
                self.loop
            )
            return None


    def process_stream_with_punctuation(self, stream_response, session_id):
        """
        处理流式响应，按标点符号分割返回数据

        Args:
            stream_response: OpenAI流式响应对象
            session_id: 会话ID

        Yields:
            tuple: (内容, 工具调用)
        """
        first = True
        buffer = ""  # 添加缓冲区
        # 标记是否已经处理完前10个字符
        first_10_chars_processed = False
        tool_calls = None

        for chunk in stream_response:
            logger.bind(tag=TAG).info(f"chunk: {chunk}")

            if getattr(chunk, "choices", None):
                content = chunk.choices[0].delta.content
                logger.bind(tag=TAG).info(f"tool_calls: {chunk.choices[0].delta.tool_calls}")
                tool_calls = chunk.choices[0].delta.tool_calls

                if tool_calls:
                    print(f"检测到工具直接返回:{tool_calls}")
                    yield content, tool_calls

                if content:
                    if not first_10_chars_processed:
                        # 前10个字符缓存处理
                        buffer += content
                        if len(buffer) >= 10:
                            first_10_chars_processed = True
                            send_buffer = buffer[:len(buffer)]

                            # 发送start开始
                            if first:
                                asyncio.run_coroutine_threadsafe(
                                    self.ws.send(json.dumps({
                                        "type": "tts",
                                        "state": "start",
                                        "session_id": session_id
                                    })),
                                    self.loop,
                                )
                                first = False

                            # 发送前10个字符
                            asyncio.run_coroutine_threadsafe(
                                self.ws.send(json.dumps({
                                    "type": "tts",
                                    "state": "sentence_start",
                                    "session_id": session_id,
                                    "text": send_buffer
                                })),
                                self.loop,
                            )

                            yield send_buffer, tool_calls
                    else:
                        # 10个字符之后的内容直接输出
                        if first:
                            asyncio.run_coroutine_threadsafe(
                                self.ws.send(json.dumps({
                                    "type": "tts",
                                    "state": "start",
                                    "session_id": session_id
                                })),
                                self.loop,
                            )
                            first = False

                        # 发送当前内容
                        asyncio.run_coroutine_threadsafe(
                            self.ws.send(json.dumps({
                                "type": "tts",
                                "state": "sentence_start",
                                "session_id": session_id,
                                "text": content
                            })),
                            self.loop,
                        )

                        yield content, tool_calls

            elif isinstance(getattr(chunk, "usage", None), CompletionUsage):
                usage_info = getattr(chunk, "usage", None)
                logger.bind(tag=TAG).info(
                    f"Token 消耗：输入 {getattr(usage_info, 'prompt_tokens', '未知')}，"
                    f"输出 {getattr(usage_info, 'completion_tokens', '未知')}，"
                    f"共计 {getattr(usage_info, 'total_tokens', '未知')}"
                )

        # 处理最后剩余的内容
        if buffer and first_10_chars_processed is False:
            if first:
                asyncio.run_coroutine_threadsafe(
                    self.ws.send(json.dumps({
                        "type": "tts",
                        "state": "start",
                        "session_id": session_id
                    })),
                    self.loop,
                )

            asyncio.run_coroutine_threadsafe(
                self.ws.send(json.dumps({
                    "type": "tts",
                    "state": "sentence_start",
                    "session_id": session_id,
                    "text": buffer
                })),
                self.loop,
            )

            print(f"处理最后剩余的内容：{buffer}")

            yield buffer, tool_calls

    def vllm_chat_response(self, dialogue, imgUrl):
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

        # 提取最后的用户消息内容
        original_text = ""
        for i in range(len(dialogue) - 1, -1, -1):
            if dialogue[i].get("role") == "user":
                original_text = dialogue[i].get("content", "")
                if not original_text or not original_text.strip():
                    original_text = self.default_vllm_user_msg  # 默认文本
                break

        # 构建视觉识别的完整对话
        dialogue = [
            {
                "role": "system",
                "content": self.build_vllm_system_prompt()
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": original_text},
                    {"type": "image_url", "image_url": {"url": imgUrl}}
                ]
            }
        ]

        logger.bind(tag=TAG).info(f"imgUrl: {imgUrl}")
        logger.bind(tag=TAG).info(f"dialogue: {dialogue}")

        return dialogue

    def init_args(self, **args):
        self.headers = args.get("headers")
        self.ws = args.get("ws")
        self.conn = args.get("conn")
