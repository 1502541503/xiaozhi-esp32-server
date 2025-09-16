from config.logger import setup_logging
from openai import OpenAI
import json
import asyncio
from openai.types import CompletionUsage
from core.providers.llm.base import LLMProviderBase

TAG = __name__
logger = setup_logging()


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        self.loop = asyncio.get_event_loop()
        self.headers = None
        self.ws = None
        self.isAiOnline = None

        self.model_name = config.get("model_name")
        self.base_url = config.get("base_url", "http://localhost:11434")
        # Initialize OpenAI client with Ollama base URL
        # 如果没有v1，增加v1
        if not self.base_url.endswith("/v1"):
            self.base_url = f"{self.base_url}/v1"

        self.client = OpenAI(
            base_url=self.base_url,
            api_key="ollama",  # Ollama doesn't need an API key but OpenAI client requires one
        )

        # 检查是否是qwen3模型
        self.is_qwen3 = self.model_name and self.model_name.lower().startswith("qwen3")

    def response(self, session_id, dialogue, **kwargs):
        try:
            # 如果是qwen3模型，在用户最后一条消息中添加/no_think指令
            if self.is_qwen3:
                # 复制对话列表，避免修改原始对话
                dialogue_copy = dialogue.copy()

                # 找到最后一条用户消息
                for i in range(len(dialogue_copy) - 1, -1, -1):
                    if dialogue_copy[i]["role"] == "user":
                        # 在用户消息前添加/no_think指令
                        dialogue_copy[i]["content"] = (
                                "/no_think " + dialogue_copy[i]["content"]
                        )
                        logger.bind(tag=TAG).debug(f"为qwen3模型添加/no_think指令")
                        break

                # 使用修改后的对话
                dialogue = dialogue_copy

            responses = self.client.chat.completions.create(
                model=self.model_name, messages=dialogue, stream=True
            )
            is_active = True
            # 用于处理跨chunk的标签
            buffer = ""

            for chunk in responses:
                try:
                    delta = (
                        chunk.choices[0].delta
                        if getattr(chunk, "choices", None)
                        else None
                    )
                    content = delta.content if hasattr(delta, "content") else ""

                    if content:
                        # 将内容添加到缓冲区
                        buffer += content

                        # 处理缓冲区中的标签
                        while "<think>" in buffer and "</think>" in buffer:
                            # 找到完整的<think></think>标签并移除
                            pre = buffer.split("<think>", 1)[0]
                            post = buffer.split("</think>", 1)[1]
                            buffer = pre + post

                        # 处理只有开始标签的情况
                        if "<think>" in buffer:
                            is_active = False
                            buffer = buffer.split("<think>", 1)[0]

                        # 处理只有结束标签的情况
                        if "</think>" in buffer:
                            is_active = True
                            buffer = buffer.split("</think>", 1)[1]

                        # 如果当前处于活动状态且缓冲区有内容，则输出
                        if is_active and buffer:
                            yield buffer
                            buffer = ""  # 清空缓冲区

                except Exception as e:
                    logger.bind(tag=TAG).error(f"Error processing chunk: {e}")

        except Exception as e:
            logger.bind(tag=TAG).error(f"Error in Ollama response generation: {e}")
            yield "【Ollama服务响应异常】"

    def response_with_functions(self, session_id, dialogue, functions=None, imgUrl=None):
        try:
            # 如果是qwen3模型，在用户最后一条消息中添加/no_think指令
            if self.is_qwen3:
                # 复制对话列表，避免修改原始对话
                dialogue_copy = dialogue.copy()

                # 找到最后一条用户消息
                for i in range(len(dialogue_copy) - 1, -1, -1):
                    if dialogue_copy[i]["role"] == "user":
                        # 在用户消息前添加/no_think指令
                        dialogue_copy[i]["content"] = (
                                "/no_think " + dialogue_copy[i]["content"]
                        )
                        logger.bind(tag=TAG).debug(f"为qwen3模型添加/no_think指令")
                        break

                # 使用修改后的对话
                dialogue = dialogue_copy

            stream_response = self.client.chat.completions.create(
                model=self.model_name,
                messages=dialogue,
                stream=True,
                tools=functions,
            )

            # 使用封装的流式处理方法
            yield from self.process_stream_with_punctuation(stream_response, session_id)

        except Exception as e:
            logger.bind(tag=TAG).error(f"Error in Ollama function call: {e}")
            yield f"【Ollama服务响应异常: {str(e)}】", None

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

        # 处理最后剩余的内容（如果没有标点符号）
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

    def init_args(self, **args):
        self.headers = args.get("headers")
        self.ws = args.get("ws")
