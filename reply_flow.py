"""Reply UI flow: preserve input and visible history when generation fails."""
from space_bridge import BridgeError


def submit_reply(bridge, username, sid, message):
    if not username:
        return None, message, "Please sign in again before sending your reply."
    if not sid:
        return None, message, "Start or resume a conversation first."
    try:
        result = bridge.message(username, sid, message)
    except BridgeError as error:
        return None, message, str(error)
    try:
        current = bridge.resume(username, sid)
    except BridgeError:
        return None, message, ("The reply was processed, but the saved conversation could not be displayed. "
                               "Use Find my conversations to reopen it before sending again.")
    status = "Ready for your reply."
    if result.get("max_turns_reached"):
        status = "Conversation limit reached. Please end the conversation and leave feedback."
    return current["history"], "", status
