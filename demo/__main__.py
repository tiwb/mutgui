"""python -m demo — 启动 Gallery 服务器。"""

import os

from demo.framework._server import run_gallery

port = int(os.environ.get("PORT", 8080))
run_gallery(port=port)
