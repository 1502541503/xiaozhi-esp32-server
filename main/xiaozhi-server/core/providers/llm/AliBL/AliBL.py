from config.logger import setup_logging
from http import HTTPStatus
from dashscope import Application
from core.providers.llm.base import LLMProviderBase
from core.utils.util import check_model_key

TAG = __name__
logger = setup_logging()


class LLMProvider(LLMProviderBase):
    def __init__(self, config):
        print("图像识别 AliBL：", "111")
        self.provider = config.get("type", "AliBL")
        self.api_key = config["api_key"]
        self.app_id = config["app_id"]
        self.base_url = config.get("base_url")
        self.is_No_prompt = config.get("is_no_prompt")
        self.memory_id = config.get("ali_memory_id")
        check_model_key("AliBLLLM", self.api_key)

    def response(self, session_id, dialogue, imgurl=None):
        print("图像识别 AliBL：", "111")
        try:
            # 处理dialogue
            if self.is_No_prompt:
                dialogue.pop(0)
                logger.bind(tag=TAG).debug(
                    f"【阿里百练API服务】处理后的dialogue: {dialogue}"
                )

            # 构造调用参数
            call_params = {
                "api_key": self.api_key,
                "app_id": self.app_id,
                "session_id": session_id,
                "messages": dialogue,
                "stream": True,
                "flow_stream_mode": "agent_format",  # 或 "full_thoughts"
                "incremental_output": True,
            }

            # 如果传入图片 URL，则包装成列表传给 image_list
            if imgurl:
                call_params["image_list"] = [imgurl]
                logger.bind(tag=TAG).debug(
                    f"【阿里百练API服务】附加图片链接: {imgurl}"
                )


            if self.memory_id != False:
                # 百练memory需要prompt参数
                prompt = dialogue[-1].get("content")
                call_params["memory_id"] = self.memory_id
                call_params["prompt"] = prompt
                logger.bind(tag=TAG).debug(
                    f"【阿里百练API服务】处理后的prompt: {prompt}"
                )

            stream_responses = Application.call(**call_params)

            for res in stream_responses:
                if res.status_code != HTTPStatus.OK:
                    logger.bind(tag=TAG).error(
                        f"【阿里百练API服务异常】code={res.status_code}, message={res.message}, request_id={res.request_id}"
                    )
                    yield f"【阿里百练API服务响应异常】{res.message}"
                    break
                else:
                    yield res.output.text

            # responses = Application.call(**call_params)
            # if responses.status_code != HTTPStatus.OK:
            #     logger.bind(tag=TAG).error(
            #         f"code={responses.status_code}, "
            #         f"message={responses.message}, "
            #         f"请参考文档：https://help.aliyun.com/zh/model-studio/developer-reference/error-code"
            #     )
            #     yield "【阿里百练API服务响应异常】"
            # else:
            #     logger.bind(tag=TAG).debug(
            #         f"【阿里百练API服务】构造参数: {call_params}"
            #     )
            #     yield responses.output.text

            # stream_responses = Application.call(**call_params)
            #
            # is_active = True
            # for res in stream_responses:
            #     if hasattr(res, "status_code") and res.status_code != HTTPStatus.OK:
            #         logger.bind(tag=TAG).error(
            #             f"【阿里百练API服务异常】code={res.status_code}, message={res.message}, request_id={res.request_id}"
            #         )
            #         yield "【阿里百练API服务响应异常】"
            #         break
            #
            #     try:
            #         # 尝试从 output.text 提取
            #         if hasattr(res, "output") and hasattr(res.output, "text"):
            #             content = res.output.text
            #         # 如果不存在，则尝试从 choices[0].delta.content 提取
            #         elif hasattr(res, "choices") and res.choices:
            #             delta = res.choices[0].delta
            #             content = delta.content if hasattr(delta, "content") else ""
            #         else:
            #             content = ""
            #     except Exception as e:
            #         logger.bind(tag=TAG).warning(f"【流式响应提取异常】{e}")
            #         content = ""
            #
            #     if content:
            #         if "<think>" in content:
            #             is_active = False
            #             content = content.split("<think>")[0]
            #         if "</think>" in content:
            #             is_active = True
            #             content = content.split("</think>")[-1]
            #         if is_active:
            #             yield content


        except Exception as e:
            logger.bind(tag=TAG).error(f"【阿里百练API服务】响应异常: {e}")
            yield "【LLM服务响应异常】"

    def response_with_functions(self, session_id, dialogue, functions=None):
        logger.bind(tag=TAG).error(
            f"阿里百练暂未实现完整的工具调用（function call），建议使用其他意图识别"
        )
