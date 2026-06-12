import json
import shlex
import subprocess
from pathlib import Path
from typing import Any


class RuntimeControlService:
    def __init__(
        self,
        *,
        config_path: str,
        validate_command: str | None,
        apply_command: str | None,
    ):
        self.config_path = Path(config_path)
        self.validate_command = validate_command
        self.apply_command = apply_command

    def write_config(self, config: dict[str, Any]) -> str:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(config, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return str(self.config_path)

    def validate(self) -> dict[str, Any]:
        return self._run_command(self.validate_command, "validate")

    def apply(self) -> dict[str, Any]:
        return self._run_command(self.apply_command, "apply")

    def _run_command(self, command: str | None, action: str) -> dict[str, Any]:
        if not command:
            return {"action": action, "status": "skipped", "command": None}
        completed = subprocess.run(
            shlex.split(command),
            check=False,
            capture_output=True,
            text=True,
        )
        result = {
            "action": action,
            "status": "ok" if completed.returncode == 0 else "error",
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
        if completed.returncode != 0:
            raise RuntimeError(json.dumps(result, sort_keys=True))
        return result
