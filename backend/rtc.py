# RT Blueprints - RT Connection

from typing import Literal, Union, Any, Tuple

from asyncio import Event

from sanic.log import logger
from sanic import Request

from .rt_module.src import rtc
from .utils import is_okip


def on_load(app):
    app.ctx.app = app
    app.ctx.rtc_ready = Event()
    @app.websocket("/rtc")
    @is_okip(app.ctx)
    class RTConnection(rtc.RTConnection):

        NAME = "Backend"

        def __init__(self, request: Request):
            super().__init__(self.NAME, loop=request.app.loop)
            request.app.ctx.rtc = self
            request.app.ctx.env.extends["rtc"] = self
            request.app.ctx.rtc_ready.set()
            self.set_event(self._logger, "logger")

        def __new__(cls, request: Request, ws, *args, **kwargs):
            self = super().__new__(cls)
            self.__init__(request)
            return self.communicate(ws, True)

        def logger(
            self, mode: Union[Literal["info", "debug", "warn", "error"], str],
            word: str, *args, **kwargs
        ) -> Any:
            "ログ出力をします。"
            return getattr(logger, mode)(f"[RTConnection] {word}", *args, **kwargs)

        async def _logger(self, data: Tuple[str, str]) -> None:
            return self.logger(*data)