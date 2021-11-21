# RT.Blueprints.API - Dashboard

from typing import TypedDict, Literal, Union, Dict, Tuple, List

from backend import (
    TypedBlueprint, TypedSanic, exceptions, Request, WebSocket, logger
)
from backend.utils import (
    DataEvent, api, cooldown, is_okip, try_loads, DEFAULT_GET_REMOTE_ADDR
)

import asyncio


class CommandData(TypedDict):
    help: str
    headding: Union[Dict[Literal["ja", "en"], str], None]
    kwargs: Dict[str, Tuple[Union[str, bool, int, float, List[str]], str, bool]]
    display_name: str
    sub_category: str


class Datas(TypedDict):
    user: Dict[str, CommandData]
    guild: Dict[str, CommandData]


class CommandRunData(TypedDict, total=False):
    command: str
    kwargs: Dict[str, str]
    category: str
    guild_id: Union[int, Literal[0]]
    user_id: int


class NewTypedBlueprint(TypedBlueprint):
    data: Datas
    queues: Dict[str, DataEvent]
    doing: Dict[str, DataEvent]


bp = NewTypedBlueprint("API.Dashboard", "/settings")
bp.data = {}
bp.queues = {}
bp.doing = {}


def on_load(app: TypedSanic):
    @bp.post("/commands/update")
    @is_okip(bp)
    async def update_settings(request: Request):
        "設定項目を更新するためのRouteです。"
        bp.data = try_loads(request)
        return api("ok", None)


    @bp.get("/commands/get/<category>")
    @cooldown(bp, 0.5)
    async def get_settings(request: Request, category: str):
        "設定一覧を返すRouteですl"
        if category in bp.data:
            return api("ok", bp.data[category])
        raise exceptions.SanicException("そのカテゴリーが見つかりませんでした。", 400)


    @bp.get("/guilds")
    @app.ctx.oauth.require_login(True)
    async def get_guilds(request: app.ctx.oauth.TypedRequest):
        "サーバー一覧を取得するためのエンドポイントです。"
        if request.ctx.user:
            return api(
                "ok", await request.app.ctx.fetch_guilds(
                    request.ctx.user.id
                )
            )
        else:
            raise exceptions.Forbidden(
                "あなたはログインしていないのでこのエンドポイントを使用することができません。"
            )


    @bp.websocket("/websocket")
    @is_okip(bp)
    class SettingsWebSocket(WebSocket):
        "何かダッシュボードからの設定がされた際にBotに伝えるためのWebSocket通信をするクラスです。"

        async def on_ready(self, _):
            while self.running == "ok" and not bp.queues:
                await asyncio.sleep(0.01)
            else:
                for ip, event in list(bp.queues.items()):
                    await self.send("on_post", event.data)
                    try:
                        await asyncio.wait_for(self.recv(), timeout=1.5)
                    except asyncio.TimeoutError:
                        logger.warn(f"Timeout setting websocket on receiving : {event.data}")
                        if ip in bp.doing:
                            del bp.doing[ip]
                    else:
                        bp.doing[ip] = event
                    finally:
                        del bp.queues[ip]
                await self.send("on_posted", "")


    @bp.post("/reply/<ip>")
    @is_okip(bp)
    async def setting_reply(request: Request, ip: str):
        "返信内容をBotから受け取るためのRouteです。"
        data = try_loads(request)["data"]
        if isinstance(data, dict):
            data = f"# {data['title']}\n{data['description']}"
        if ip in bp.doing:
            bp.doing[ip].set(data)
            del bp.doing[ip]
            return api("ok", None)
        else:
            raise exceptions.SanicException("その返信先が見つかりませんでした。", 400)


    @bp.post("/update")
    @cooldown(bp, 0.5)
    @app.ctx.oauth.require_login(True)
    async def setting(request: app.ctx.oauth.TypedRequest):
        "設定を更新するためのRouteです。"
        if request.ctx.user:
            if ((ip := DEFAULT_GET_REMOTE_ADDR(request)) in bp.queues
                    or ip in bp.doing):
                raise exceptions.SanicException(
                    "現在別で設定変更の処理を実行しているためこの処理を実行できません。", 423
                )
            else:
                event = DataEvent(loop=request.app.loop)
                try:
                    event.data = try_loads(request)
                except Exception as e:
                    event.set("error")
                    raise e
                if all(
                    key in event.data for key in CommandRunData.__annotations__
                ):
                    bp.queues[ip] = event
                    event.data["ip"] = ip
                    try:
                        data = await asyncio.wait_for(
                            event.wait(), timeout=8
                        )
                    except asyncio.TimeoutError:
                        if ip in bp.doing:
                            del bp.doing[ip]
                        if ip in bp.queues:
                            del bp.queues[ip]
                        raise exceptions.RequestTimeout(
                            "タイムアウトしました。"
                        )
                    else:
                        return api("ok", data)
                else:
                    # もし必要なデータがないのならエラーを起こす。
                    raise exceptions.SanicException(
                        "必要なデータが不足しています。", 500
                    )
        else:
            raise exceptions.SanicException(
                "このAPIを使用するにはログインをしている必要があります。", 403
            )