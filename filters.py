STUCK_WORDS = [
    "다시", "안돼", "안 돼", "안되", "에러", "이상해", "왜",
    "오류", "fail", "error", "broken", "안 됨", "왜 안",
]

MIN_PROMPTS = 3
MIN_EDITS   = 2

TOOLS_THAT_EDIT = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

SLASH_COMMAND_PREFIXES = (
    "<command-name>",
    "<command-message>",
    "<local-command-stdout>",
    "<task-notification>",
    "<function_results>",
    "<system-reminder>",
)

INTERRUPTED_PREFIX = "[Request interrupted by user]"
