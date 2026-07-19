from __future__ import annotations

from typer.testing import CliRunner

from prd_agent import cli


class FakeRepository:
    password_hash: str | None = None

    def reset_admin_password(self, password_hash: str) -> bool:
        self.password_hash = password_hash
        return True


def test_reset_admin_password_hashes_input(monkeypatch) -> None:
    repository = FakeRepository()
    monkeypatch.setattr(cli, "get_settings", lambda: object())
    monkeypatch.setattr(cli, "_repository", lambda settings: repository)

    result = CliRunner().invoke(
        cli.app,
        ["reset-admin-password"],
        input="new-secure-password\nnew-secure-password\n",
    )

    assert result.exit_code == 0
    assert repository.password_hash is not None
    assert repository.password_hash != "new-secure-password"
    assert cli.PasswordHash.recommended().verify(
        "new-secure-password",
        repository.password_hash,
    )
    assert "所有现有登录会话已失效" in result.output


def test_reset_admin_password_rejects_short_password(monkeypatch) -> None:
    repository = FakeRepository()
    monkeypatch.setattr(cli, "get_settings", lambda: object())
    monkeypatch.setattr(cli, "_repository", lambda settings: repository)

    result = CliRunner().invoke(
        cli.app,
        ["reset-admin-password"],
        input="short\nshort\n",
    )

    assert result.exit_code == 1
    assert repository.password_hash is None
    assert "密码长度必须为 8 至 128 个字符" in result.output
