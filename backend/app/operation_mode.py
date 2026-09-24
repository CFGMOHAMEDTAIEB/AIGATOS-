import os

VALID_OPERATION_MODES = {"readonly_demo", "live_simulation"}


def get_operation_mode() -> str:
    mode = os.getenv("AIGATOS_OPERATION_MODE", "live_simulation").strip().lower()
    if mode not in VALID_OPERATION_MODES:
        raise RuntimeError("AIGATOS_OPERATION_MODE must be readonly_demo or live_simulation")
    return mode


def capabilities() -> dict[str, bool | str]:
    mode = get_operation_mode()
    live = mode == "live_simulation"
    return {
        "operation_mode": mode,
        "can_create_simulation": live,
        "can_launch_simulation": live,
        "can_start_investigation": live,
        "can_review_recommendations": live,
        "can_execute_real_ota": False,
    }
