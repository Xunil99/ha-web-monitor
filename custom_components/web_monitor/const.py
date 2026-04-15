"""Constants for the Web Monitor integration."""

DOMAIN = "web_monitor"

CONF_MONITOR_NAME = "monitor_name"
CONF_STEPS = "steps"
CONF_TARGET_SELECTOR = "target_selector"
CONF_TARGET_EXTRACT = "target_extract"
CONF_INTERVAL = "interval"
CONF_SAVE_SCREENSHOTS = "save_screenshots"
CONF_HISTORY_DAYS = "history_days"
CONF_TIMEOUT = "timeout"
CONF_PERSIST_SESSION = "persist_session"

DEFAULT_INTERVAL = 3600
DEFAULT_TIMEOUT = 60
DEFAULT_HISTORY_DAYS = 90
DEFAULT_SAVE_SCREENSHOTS = False
DEFAULT_PERSIST_SESSION = True

EXTRACT_TEXT = "text_content"
EXTRACT_INNER_HTML = "inner_html"
EXTRACT_ATTRIBUTE = "attribute"

STEP_GOTO = "goto"
STEP_CLICK = "click"
STEP_FILL = "fill"
STEP_WAIT = "wait"
STEP_SELECT = "select"
