from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.platform import MessageType

@register("helloworld", "YourName", "一个简单的 Hello World 插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 存储已注册的群组信息
        self.registered_groups: dict[str, str] = {}  # group_id -> session_id

    async def initialize(self):
        """可选择实现异步的插件初始化方法，当实例化该插件类之后会自动调用该方法。"""

    # 注册指令的装饰器。指令名为 helloworld。注册成功后，发送 `/helloworld` 就会触发这个指令，并回复 `你好, {user_name}!`
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """这是一个 hello world 指令""" # 这是 handler 的描述，将会被解析方便用户了解插件内容。建议填写。
        user_name = event.get_sender_name()
        message_str = event.message_str # 用户发的纯文本消息字符串
        message_chain = event.get_messages() # 用户所发的消息的消息链 # from astrbot.api.message_components import *
        logger.info(message_chain)
        yield event.plain_result(f"平台, {event.get_platform_name()}Hello, {user_name}, 你发了 {message_str}!") # 发送一条纯文本消息

    @filter.command("register_group")
    async def register_group(self, event: AstrMessageEvent):
        """注册当前群聊，存储会话信息以便后续主动发送消息。"""
        platform_name = event.get_platform_name()
        
        # 检查是否在群聊中
        if event.get_group_id() is None:
            yield event.plain_result("此指令只能在群聊中使用")
            return
        
        group_id = event.get_group_id()
        session_id = event.session_id
        
        # 存储群组信息
        self.registered_groups[group_id] = session_id
        
        # 获取平台适配器并记录会话信息
        try:
            platform = self.context.get_platform(platform_name)
            if platform and hasattr(platform, 'remember_session_scene'):
                platform.remember_session_scene(session_id, "group")
                logger.info(f"[MC_Hack_Mod] 注册群组: {group_id}, session_id: {session_id}")
                yield event.plain_result(f"群组 {group_id} 已注册，可用于主动消息发送")
            else:
                yield event.plain_result("平台适配器不支持会话记录功能")
        except Exception as e:
            logger.error(f"[MC_Hack_Mod] 注册群组失败: {e}")
            yield event.plain_result(f"注册失败: {str(e)}")

    @filter.command("list_groups")
    async def list_groups(self, event: AstrMessageEvent):
        """列出所有已注册的群组。"""
        if not self.registered_groups:
            yield event.plain_result("暂无已注册的群组")
            return
        
        groups_info = "\n".join([f"群组 {gid}: {sid}" for gid, sid in self.registered_groups.items()])
        yield event.plain_result(f"已注册的群组:\n{groups_info}")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
