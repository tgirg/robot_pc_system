from __future__ import annotations

from dataclasses import dataclass

from .robot_command import RobotCommand, format_command


@dataclass(frozen=True)
class CommandSendResult:
    success: bool
    message: str
    sent_text: str


class BaseCommandSender:
    def send(self, command: RobotCommand) -> CommandSendResult:
        raise NotImplementedError


class MockCommandSender(BaseCommandSender):
    def __init__(self) -> None:
        self.sent_commands: list[str] = []

    def send(self, command: RobotCommand) -> CommandSendResult:
        text = format_command(command)
        self.sent_commands.append(text)
        return CommandSendResult(True, f"Mock送信: {text}", text)


class SerialCommandSender(BaseCommandSender):
    def __init__(self, serial_client) -> None:
        self.serial_client = serial_client

    def send(self, command: RobotCommand) -> CommandSendResult:
        text = format_command(command)
        try:
            ok, message = self.serial_client.send_command(text)
        except Exception as exc:
            return CommandSendResult(False, f"送信失敗: {exc}", text)

        if not ok:
            if "NG" in message or "Not connected" in message:
                return CommandSendResult(False, "送信失敗: ESP32未接続", text)
            return CommandSendResult(False, f"送信失敗: {message}", text)
        return CommandSendResult(True, message, text)
