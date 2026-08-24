"""Command line entrypoint."""

from __future__ import annotations

from .app import ControllerApp, build_arg_parser, print_controller_list, print_node_list
from .controller_input import print_controller_debug


def main() -> None:
    """Run the controller application."""
    args = build_arg_parser().parse_args()
    try:
        if args.list_controllers:
            print_controller_list()
            return
        if args.list_nodes:
            print_node_list(args.discovery_timeout, args.node_manifest)
            return
        if args.debug_controller is not None:
            print_controller_debug(args.debug_controller)
            return
        ControllerApp(args).start()
    except KeyboardInterrupt:
        print("stopped by Ctrl+C")
    except RuntimeError as exc:
        raise SystemExit(f"error: {exc}") from exc


if __name__ == "__main__":
    main()
