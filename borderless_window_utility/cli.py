from __future__ import annotations

import argparse
import logging

from .core import WINDOW_TITLE, try_auto_borderless


logging.basicConfig(level=logging.INFO, format="[%(levelname)s]: %(message)s")


def get_configs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=WINDOW_TITLE)
    parser.add_argument(
        "-a",
        "--apply-and-exit",
        action="store_true",
        default=False,
        dest="apply_and_exit",
        help="Automatically apply borderless window and exit (no UI)",
    )
    return parser.parse_args()


def main() -> None:
    args = get_configs()
    if args.apply_and_exit:
        raise SystemExit(0 if try_auto_borderless() else 1)

    from .textual_app import BorderlessWindowApp

    BorderlessWindowApp().run()


def headless_main() -> None:
    raise SystemExit(0 if try_auto_borderless() else 1)


if __name__ == "__main__":
    main()
