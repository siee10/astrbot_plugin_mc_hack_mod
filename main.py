from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.platform import MessageType
from astrbot.core.star.star_tools import StarTools
import json
import asyncio
from aiohttp import web

@register("helloworld", "YourName", "一个简单的 Hello World 插件", "1.0.0")
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 存储已注册的群组信息: group_id -> {session_id, platform_name}
        self.registered_groups: dict[str, dict] = {}
        # 数据文件路径
        self.data_file = StarTools.get_data_dir() / "registered_groups.json"
        # HTTP服务器相关
        self.http_runner = None
        self.http_site = None

    async def initialize(self):
        """加载已注册的群组信息并启动HTTP服务器。"""
        await self._load_groups()
        await self._start_http_server()

    async def _start_http_server(self):
        """启动HTTP服务器，监听8082端口。"""
        try:
            app = web.Application()
            app.router.add_get('/health', self._handle_health)
            app.router.add_post('/sendMsg', self._handle_send_msg)
            
            self.http_runner = web.AppRunner(app)
            await self.http_runner.setup()
            self.http_site = web.TCPSite(self.http_runner, '0.0.0.0', 8082)
            await self.http_site.start()
            logger.info("[MC_Hack_Mod] HTTP服务器已启动，监听端口 8082")
        except Exception as e:
            logger.error(f"[MC_Hack_Mod] HTTP服务器启动失败: {e}")

    async def _handle_health(self, request):
        """健康检查接口。"""
        return web.json_response({"status": "ok", "registered_groups": len(self.registered_groups)})

    async def _handle_send_msg(self, request):
        """发送消息接口,向所有已注册群组广播消息。"""
        try:
            # 获取来访者IP
            remote_ip = request.remote if request.remote else "unknown"
            logger.info(f"[MC_Hack_Mod] 收到请求 - IP: {remote_ip}")

            try:
                data = await request.json()
                logger.info(f"[MC_Hack_Mod] 请求报文: {json.dumps(data, ensure_ascii=False)}")
            except Exception:
                return web.json_response({"error": "请求体不是有效的JSON格式"}, status=400)
            
            player_name = data.get('playerName')
            msg_type = data.get('type')
            message = data.get('message')
            
            if not all([player_name, msg_type, message]):
                return web.json_response({"error": "缺少必要参数: playerName, type, message"}, status=400)
            
            if not self.registered_groups:
                return web.json_response({"error": "暂无已注册的群组"}, status=404)
            
            # 拼接消息内容
            formatted_message = f"[{msg_type}] {player_name}: {message}"
            
            from astrbot.api.event import MessageChain
            from astrbot.api.message_components import Plain
            from astrbot.core.platform.message_session import MessageSesion
            
            success_count = 0
            fail_count = 0
            
            for group_id, group_info in self.registered_groups.items():
                try:
                    session_id = group_info["session_id"]
                    platform_name = group_info["platform_name"]
                    
                    # 根据平台名称获取平台适配器
                    platform = self.context.get_platform(platform_name)
                    if not platform:
                        logger.error(f"[MC_Hack_Mod] 未找到平台适配器: {platform_name}")
                        fail_count += 1
                        continue
                    
                    # 创建消息会话
                    session = MessageSesion(
                        platform_name=platform_name,
                        message_type=MessageType.GROUP_MESSAGE,
                        session_id=session_id,
                    )
                    
                    # 创建消息链
                    message_chain = MessageChain(chain=[Plain(formatted_message)])
                    
                    # 发送消息
                    await platform.send_by_session(session, message_chain)
                    success_count += 1
                    logger.info(f"[MC_Hack_Mod] 消息发送成功: {group_id}")
                except Exception as e:
                    fail_count += 1
                    logger.error(f"[MC_Hack_Mod] 消息发送失败 {group_id}: {e}")
            
            return web.json_response({
                "success": True,
                "message": f"广播完成: 成功 {success_count} 个, 失败 {fail_count} 个"
            })
        except Exception as e:
            logger.error(f"[MC_Hack_Mod] sendMsg接口错误: {e}")
            return web.json_response({"error": str(e)}, status=500)

    async def _load_groups(self):
        """从文件加载注册的群组信息。"""
        try:
            if self.data_file.exists():
                with open(self.data_file, "r", encoding="utf-8") as f:
                    self.registered_groups = json.load(f)
                # 兼容旧数据格式: group_id -> session_id (string)
                # 新格式: group_id -> {session_id, platform_name}
                need_save = False
                for gid, val in list(self.registered_groups.items()):
                    if isinstance(val, str):
                        self.registered_groups[gid] = {
                            "session_id": val,
                            "platform_name": "unknown",
                        }
                        need_save = True
                if need_save:
                    await self._save_groups()
                    logger.warning("[MC_Hack_Mod] 检测到旧数据格式，已自动转换。旧注册的群组需要重新注册才能通过HTTP接口发送消息。")
                logger.info(f"[MC_Hack_Mod] 已加载 {len(self.registered_groups)} 个注册群组")
        except Exception as e:
            logger.error(f"[MC_Hack_Mod] 加载注册群组失败: {e}")

    async def _save_groups(self):
        """保存注册的群组信息到文件。"""
        try:
            # 确保目录存在
            self.data_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.registered_groups, f, ensure_ascii=False, indent=2)
            logger.info(f"[MC_Hack_Mod] 已保存 {len(self.registered_groups)} 个注册群组")
        except Exception as e:
            logger.error(f"[MC_Hack_Mod] 保存注册群组失败: {e}")

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
        
        # 存储群组信息（包含平台名称）
        self.registered_groups[group_id] = {
            "session_id": session_id,
            "platform_name": platform_name,
        }
        
        # 保存到文件
        await self._save_groups()
        
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

    @filter.command("unregister_group")
    async def unregister_group(self, event: AstrMessageEvent):
        """取消注册当前群聊。"""
        if event.get_group_id() is None:
            yield event.plain_result("此指令只能在群聊中使用")
            return
        
        group_id = event.get_group_id()
        
        if group_id not in self.registered_groups:
            yield event.plain_result(f"群组 {group_id} 未注册")
            return
        
        # 删除群组信息
        del self.registered_groups[group_id]
        
        # 保存到文件
        await self._save_groups()
        
        logger.info(f"[MC_Hack_Mod] 取消注册群组: {group_id}")
        yield event.plain_result(f"群组 {group_id} 已取消注册")

    @filter.command("list_groups")
    async def list_groups(self, event: AstrMessageEvent):
        """列出所有已注册的群组。"""
        if not self.registered_groups:
            yield event.plain_result("暂无已注册的群组")
            return
        
        groups_info = "\n".join([f"群组 {gid} ({info['platform_name']}): {info['session_id']}" for gid, info in self.registered_groups.items()])
        yield event.plain_result(f"已注册的群组:\n{groups_info}")

    @filter.command("test_broadcast")
    async def test_broadcast(self, event: AstrMessageEvent):
        """向所有已注册的群组发送测试消息。"""
        if not self.registered_groups:
            yield event.plain_result("暂无已注册的群组，请先使用 /register_group 注册")
            return
        
        from astrbot.api.event import MessageChain
        from astrbot.api.message_components import Plain
        from astrbot.core.platform.message_session import MessageSesion
        
        success_count = 0
        fail_count = 0
        test_message = "这是一条测试消息"
        
        for group_id, group_info in self.registered_groups.items():
            try:
                session_id = group_info["session_id"]
                platform_name = group_info["platform_name"]
                
                # 获取平台适配器
                platform = self.context.get_platform(platform_name)
                if not platform:
                    logger.error(f"[MC_Hack_Mod] 未找到平台适配器: {platform_name}")
                    fail_count += 1
                    continue
                
                # 创建消息会话
                session = MessageSesion(
                    platform_name=platform_name,
                    message_type=MessageType.GROUP_MESSAGE,
                    session_id=session_id,
                )
                
                # 创建消息链
                message_chain = MessageChain(chain=[Plain(test_message)])
                
                # 发送消息
                await platform.send_by_session(session, message_chain)
                success_count += 1
                logger.info(f"[MC_Hack_Mod] 测试消息发送成功: {group_id}")
            except Exception as e:
                fail_count += 1
                logger.error(f"[MC_Hack_Mod] 测试消息发送失败 {group_id}: {e}")
        
        yield event.plain_result(f"测试消息发送完成: 成功 {success_count} 个, 失败 {fail_count} 个")

    async def terminate(self):
        """可选择实现异步的插件销毁方法，当插件被卸载/停用时会调用。"""
        # 关闭HTTP服务器
        if self.http_site:
            await self.http_site.stop()
            logger.info("[MC_Hack_Mod] HTTP服务器已停止")
        if self.http_runner:
            await self.http_runner.cleanup()
            logger.info("[MC_Hack_Mod] HTTP服务器资源已释放")
