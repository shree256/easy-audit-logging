def push_usage_log(
    message: str,
    event: str,
    success: bool,
    error: str,
    extra: dict,
):
    """
    data:
        - message: message
        - user: user details
        - event: login or logout
        - success: true or false
        - error: error message
        - extra: {
            - cognito_id: cognito id
            - status_code: status code
        }
    """
    from .config import get_logger
    from .middleware import get_user_details

    logger = get_logger("audit.login")
    user_id, user_info = get_user_details()

    logger.login(
        message,
        user_id=user_id,
        user_info=user_info,
        event=event,
        success=success,
        error=error,
        extra=extra,
    )
