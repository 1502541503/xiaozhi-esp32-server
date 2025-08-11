import uuid
from typing import List, Dict
from datetime import datetime


class Message:
    def __init__(
        self,
        role: str,
        content: str = None,
        uniq_id: str = None,
        tool_calls=None,
        tool_call_id=None,
    ):
        self.uniq_id = uniq_id if uniq_id is not None else str(uuid.uuid4())
        self.role = role
        self.content = content
        self.tool_calls = tool_calls
        self.tool_call_id = tool_call_id


class Dialogue:
    def __init__(self):
        self.dialogue: List[Message] = []
        # 获取当前时间
        self.current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def put(self, message: Message):
        self.dialogue.append(message)

    def getMessages(self, m, dialogue):
        if m.tool_calls is not None:
            dialogue.append({"role": m.role, "tool_calls": m.tool_calls})
        elif m.role == "tool":
            dialogue.append(
                {
                    "role": m.role,
                    "tool_call_id": (
                        str(uuid.uuid4()) if m.tool_call_id is None else m.tool_call_id
                    ),
                    "content": m.content,
                }
            )
        else:
            dialogue.append({"role": m.role, "content": m.content})

    def get_llm_dialogue(self) -> List[Dict[str, str]]:
        dialogue = []
        for m in self.dialogue:
            self.getMessages(m, dialogue)
        return dialogue

    def update_system_message(self, new_content: str):
        """更新或添加系统消息"""
        # 查找第一个系统消息
        system_msg = next((msg for msg in self.dialogue if msg.role == "system"), None)
        if system_msg:
            system_msg.content = new_content
        else:
            self.put(Message(role="system", content=new_content))

    def clear_user_msg(self):
        """清除所有非system类型的消息，只保留系统消息"""
        self.dialogue = [msg for msg in self.dialogue if msg.role == "system"]

    def get_llm_dialogue_with_memory(
        self, memory_str: str = None,lon = None,lat = None
    ) -> List[Dict[str, str]]:
        # if memory_str is None or len(memory_str) == 0:
        #     #print(f"直接返回，不记忆")
        #     return self.get_llm_dialogue()

        # 构建带记忆的对话
        dialogue = []

        # 添加系统提示和记忆
        system_message = next(
            (msg for msg in self.dialogue if msg.role == "system"), None
        )

        if lon and lat:
            enhanced_system_prompt = (
                f"{system_message.content}\n\n"
                f"用户所在的经纬度location：{lon},{lat}\n"
            )
            dialogue.append({"role": "system", "content": enhanced_system_prompt})
        # if system_message:
        #     enhanced_system_prompt = (
        #         f"{system_message.content}\n\n"
        #         f"以下是用户的历史记忆：\n```\n{memory_str}\n```"
        #     )
        #     dialogue.append({"role": "system", "content": enhanced_system_prompt})

        # 获取非系统消息
        non_system_msgs = [m for m in self.dialogue if m.role != "system"]
        # 截取最近 N 轮（1轮 = 用户 + AI），从后往前找
        selected = []
        round_count = 0
        current_round = []

        # 添加用户和助手的对话
        for m in reversed(non_system_msgs):
            current_round.insert(0, m)
            if m.role == "user":
                round_count += 1
                if round_count >= 2:
                    selected = current_round + selected
                    break
                else:
                    selected = current_round + selected
                    current_round = []

            # 添加选中的对话
        for m in selected:
            self.getMessages(m, dialogue)

        return dialogue
