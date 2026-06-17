"""python -m demo — 启动 Gallery 服务器。"""

import argparse
import os

from demo.framework._server import run_gallery


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="mutgui Gallery demo")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", 8080)),
        help="Bind port",
    )
    parser.add_argument("--debug", action="store_true", help="Show debug logs in console")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_gallery(host=args.host, port=args.port, debug=args.debug)
