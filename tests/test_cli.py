from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from resume_ops_api.cli import async_main, main
from resume_ops_api.core.exceptions import ResumeValidationError
from resume_ops_api.graph.models import TailorResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_namespace(
    resume: str,
    jd: str,
    output: str,
    output_json: str | None = None,
    theme: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(
        resume=resume,
        jd=jd,
        output=output,
        output_json=output_json,
        theme=theme,
    )


def _make_tailor_result(resume: dict, pdf_path: str) -> TailorResult:
    return TailorResult(
        resume=resume,
        pdf_path=pdf_path,
        pdf_base64="ZmFrZQ==",
        theme="jsonresume-theme-stackoverflow",
        plain_text="Name: Test\n",
    )


class _FakeThemeService:
    def __init__(self, default_theme: str = "jsonresume-theme-stackoverflow") -> None:
        self.default_theme = default_theme
        self.allowed_themes = ["jsonresume-theme-stackoverflow", "jsonresume-theme-even"]

    def resolve(self, candidate: str | None) -> str:
        from resume_ops_api.services.themes import ThemeService
        return ThemeService(self.allowed_themes, self.default_theme).resolve(candidate)


class _FakeOrchestrator:
    def __init__(self, *, fail_with: Exception | None = None, result_resume: dict | None = None, pdf_path: str | None = None) -> None:
        self.fail_with = fail_with
        self._result_resume = result_resume or {"basics": {"name": "Test"}}
        self._pdf_path = pdf_path or "/tmp/fake.pdf"

    async def run(self, *, resume: dict, job_description: str, theme: str, sections: list[str] | None = None, **kwargs) -> TailorResult:
        if self.fail_with:
            raise self.fail_with
        return _make_tailor_result(self._result_resume, self._pdf_path)


class _FakeContainer:
    def __init__(
        self,
        theme_service: _FakeThemeService | None = None,
        orchestrator: _FakeOrchestrator | None = None,
    ) -> None:
        self.theme_service = theme_service or _FakeThemeService()
        self.orchestrator = orchestrator or _FakeOrchestrator()


# ---------------------------------------------------------------------------
# CLI argument parsing tests (main function)
# ---------------------------------------------------------------------------


class TestCliArgumentParsing:
    """Tests for the argparse-based CLI argument parsing."""

    def test_required_arguments_present(self) -> None:
        """main() should parse required arguments without error."""
        test_args = [
            "resume-ops",
            "--resume", "/path/to/resume.json",
            "--jd", "/path/to/jd.md",
            "--output", "/path/to/output.pdf",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("resume_ops_api.cli.asyncio.run", side_effect=SystemExit(0)):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0

    def test_missing_resume_argument(self) -> None:
        test_args = [
            "resume-ops",
            "--jd", "/path/to/jd.md",
            "--output", "/path/to/output.pdf",
        ]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code != 0

    def test_missing_jd_argument(self) -> None:
        test_args = [
            "resume-ops",
            "--resume", "/path/to/resume.json",
            "--output", "/path/to/output.pdf",
        ]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code != 0

    def test_missing_output_argument(self) -> None:
        test_args = [
            "resume-ops",
            "--resume", "/path/to/resume.json",
            "--jd", "/path/to/jd.md",
        ]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code != 0

    def test_all_arguments_including_optional(self) -> None:
        test_args = [
            "resume-ops",
            "--resume", "/path/to/resume.json",
            "--jd", "/path/to/jd.md",
            "--output", "/path/to/output.pdf",
            "--output-json", "/path/to/output.json",
            "--theme", "jsonresume-theme-even",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("resume_ops_api.cli.asyncio.run", side_effect=SystemExit(0)):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0

    def test_optional_output_json_can_be_omitted(self) -> None:
        test_args = [
            "resume-ops",
            "--resume", "/path/to/resume.json",
            "--jd", "/path/to/jd.md",
            "--output", "/path/to/output.pdf",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("resume_ops_api.cli.asyncio.run", side_effect=SystemExit(0)):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 0

    def test_keyboard_interrupt_returns_130(self) -> None:
        test_args = [
            "resume-ops",
            "--resume", "/path/to/resume.json",
            "--jd", "/path/to/jd.md",
            "--output", "/path/to/output.pdf",
        ]
        with patch.object(sys, "argv", test_args):
            with patch("resume_ops_api.cli.asyncio.run", side_effect=KeyboardInterrupt):
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 130


# ---------------------------------------------------------------------------
# async_main tests
# ---------------------------------------------------------------------------


class TestAsyncMainFileValidation:
    """Tests for file existence checks in async_main."""

    @pytest.mark.asyncio
    async def test_resume_file_not_found_returns_1(self, tmp_path: Path) -> None:
        jd_path = tmp_path / "jd.md"
        jd_path.write_text("# Job Description")
        output_path = tmp_path / "output.pdf"

        args = _make_namespace(
            resume=str(tmp_path / "nonexistent.json"),
            jd=str(jd_path),
            output=str(output_path),
        )

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            result = await async_main(args)
            assert result == 1

    @pytest.mark.asyncio
    async def test_jd_file_not_found_returns_1(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.json"
        resume_path.write_text('{"basics": {"name": "Test"}}')
        output_path = tmp_path / "output.pdf"

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(tmp_path / "nonexistent.md"),
            output=str(output_path),
        )

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            result = await async_main(args)
            assert result == 1

    @pytest.mark.asyncio
    async def test_jd_is_directory_returns_1_with_helpful_message(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.json"
        resume_path.write_text('{"basics": {"name": "Test"}}')
        jd_dir = tmp_path / "jd_dir"
        jd_dir.mkdir()
        output_path = tmp_path / "output.pdf"

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(jd_dir),
            output=str(output_path),
        )

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            result = await async_main(args)
            assert result == 1

    @pytest.mark.asyncio
    async def test_invalid_resume_json_returns_1(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.json"
        resume_path.write_text("{invalid json")
        jd_path = tmp_path / "jd.md"
        jd_path.write_text("# Job Description")
        output_path = tmp_path / "output.pdf"

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(jd_path),
            output=str(output_path),
        )

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            result = await async_main(args)
            assert result == 1


class TestAsyncMainThemeHandling:
    """Tests for theme resolution logic in async_main."""

    @pytest.mark.asyncio
    async def test_default_theme_used_when_not_provided(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.json"
        resume_path.write_text('{"basics": {"name": "Test"}}')
        jd_path = tmp_path / "jd.md"
        jd_path.write_text("# JD")
        output_path = tmp_path / "output.pdf"

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(jd_path),
            output=str(output_path),
            theme=None,
        )

        # Orchestrator must return a *different* PDF path (as in real usage)
        # to avoid shutil.copy SameFileError
        fake_pdf = tmp_path / "data" / "jobs" / "fake" / "output.pdf"
        fake_pdf.parent.mkdir(parents=True, exist_ok=True)
        fake_pdf.write_bytes(b"%PDF-1.4 fake")

        theme_service = _FakeThemeService(default_theme="jsonresume-theme-even")
        orch = _FakeOrchestrator(pdf_path=str(fake_pdf))
        container = _FakeContainer(theme_service=theme_service, orchestrator=orch)

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            with patch("resume_ops_api.cli.build_container", return_value=container):
                result = await async_main(args)
                assert result == 0
                assert output_path.exists()

    @pytest.mark.asyncio
    async def test_invalid_theme_returns_1(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.json"
        resume_path.write_text('{"basics": {"name": "Test"}}')
        jd_path = tmp_path / "jd.md"
        jd_path.write_text("# JD")
        output_path = tmp_path / "output.pdf"

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(jd_path),
            output=str(output_path),
            theme="nonexistent-theme",
        )

        container = _FakeContainer()

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            with patch("resume_ops_api.cli.build_container", return_value=container):
                result = await async_main(args)
                assert result == 1


class TestAsyncMainSuccessfulRun:
    """Tests for successful pipeline execution in async_main."""

    @pytest.mark.asyncio
    async def test_successful_generation_returns_0(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.json"
        resume_data = {"basics": {"name": "Test User", "email": "test@example.com"}}
        resume_path.write_text(json.dumps(resume_data))
        jd_path = tmp_path / "jd.md"
        jd_path.write_text("# Job Description\nSeeking a senior engineer.")
        output_path = tmp_path / "out" / "output.pdf"

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(jd_path),
            output=str(output_path),
        )

        # Create a fake orchestrator that produces a known PDF
        fake_pdf = tmp_path / "data" / "jobs" / "fake-job" / "output.pdf"
        fake_pdf.parent.mkdir(parents=True, exist_ok=True)
        fake_pdf.write_bytes(b"%PDF-1.4\n% Fake test PDF\n")

        orch = _FakeOrchestrator(pdf_path=str(fake_pdf), result_resume=resume_data)
        container = _FakeContainer(orchestrator=orch)

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            with patch("resume_ops_api.cli.build_container", return_value=container):
                result = await async_main(args)
                assert result == 0
                assert output_path.exists()
                assert output_path.read_bytes()[:5] == b"%PDF-"

    @pytest.mark.asyncio
    async def test_successful_generation_with_output_json(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.json"
        resume_data = {"basics": {"name": "Test User", "email": "test@example.com"}}
        resume_path.write_text(json.dumps(resume_data))
        jd_path = tmp_path / "jd.md"
        jd_path.write_text("# JD")
        output_path = tmp_path / "output.pdf"
        output_json_path = tmp_path / "output.json"

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(jd_path),
            output=str(output_path),
            output_json=str(output_json_path),
        )

        fake_pdf = tmp_path / "data" / "jobs" / "fake-job" / "output.pdf"
        fake_pdf.parent.mkdir(parents=True, exist_ok=True)
        fake_pdf.write_bytes(b"%PDF-1.4 fake")

        orch = _FakeOrchestrator(pdf_path=str(fake_pdf), result_resume=resume_data)
        container = _FakeContainer(orchestrator=orch)

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            with patch("resume_ops_api.cli.build_container", return_value=container):
                result = await async_main(args)
                assert result == 0
                assert output_json_path.exists()
                written = json.loads(output_json_path.read_text(encoding="utf-8"))
                assert written == resume_data

    @pytest.mark.asyncio
    async def test_data_dir_fallback_for_local_usage(self, tmp_path: Path) -> None:
        """When /data is not writable, fall back to ./data."""
        resume_path = tmp_path / "resume.json"
        resume_path.write_text('{"basics": {"name": "Test"}}')
        jd_path = tmp_path / "jd.md"
        jd_path.write_text("# JD")
        output_path = tmp_path / "output.pdf"

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(jd_path),
            output=str(output_path),
        )

        fake_pdf = tmp_path / "data" / "fake-job" / "output.pdf"
        fake_pdf.parent.mkdir(parents=True, exist_ok=True)
        fake_pdf.write_bytes(b"%PDF-1.4 fake")

        orch = _FakeOrchestrator(pdf_path=str(fake_pdf))
        container = _FakeContainer(orchestrator=orch)

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            # Simulate default /data dir settings that can't write to /data
            mock_settings = MagicMock()
            mock_settings.data_dir = Path("/data")
            mock_get_settings.return_value = mock_settings

            # Mock Path("/data").exists() to return False
            with patch.object(Path, "exists", return_value=False):
                with patch("resume_ops_api.cli.build_container", return_value=container):
                    result = await async_main(args)
                    assert result == 0
                    # The data_dir should have been changed to ./data
                    assert mock_settings.data_dir == Path("./data")


class TestAsyncMainErrorHandling:
    """Tests for error handling paths in async_main."""

    @pytest.mark.asyncio
    async def test_resume_validation_error_returns_1(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.json"
        resume_path.write_text('{"basics": {"name": "Test"}}')
        jd_path = tmp_path / "jd.md"
        jd_path.write_text("# JD")
        output_path = tmp_path / "output.pdf"

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(jd_path),
            output=str(output_path),
        )

        validation_error = ResumeValidationError(
            "The input resume failed JSON Resume schema validation.",
            details={
                "context": "input resume",
                "errors": [
                    {"path": "basics.email", "message": "Invalid email format"},
                    {"path": "basics.url", "message": "Invalid URL format"},
                ],
            },
        )
        orch = _FakeOrchestrator(fail_with=validation_error)
        container = _FakeContainer(orchestrator=orch)

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            with patch("resume_ops_api.cli.build_container", return_value=container):
                result = await async_main(args)
                assert result == 1

    @pytest.mark.asyncio
    async def test_generic_exception_returns_1(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.json"
        resume_path.write_text('{"basics": {"name": "Test"}}')
        jd_path = tmp_path / "jd.md"
        jd_path.write_text("# JD")
        output_path = tmp_path / "output.pdf"

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(jd_path),
            output=str(output_path),
        )

        orch = _FakeOrchestrator(fail_with=RuntimeError("Unexpected failure"))
        container = _FakeContainer(orchestrator=orch)

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            with patch("resume_ops_api.cli.build_container", return_value=container):
                result = await async_main(args)
                assert result == 1

    @pytest.mark.asyncio
    async def test_pdf_not_generated_returns_1(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.json"
        resume_path.write_text('{"basics": {"name": "Test"}}')
        jd_path = tmp_path / "jd.md"
        jd_path.write_text("# JD")
        output_path = tmp_path / "output.pdf"

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(jd_path),
            output=str(output_path),
        )

        # Orchestrator returns a non-existent PDF path
        orch = _FakeOrchestrator(pdf_path="/nonexistent/path/fake.pdf")
        container = _FakeContainer(orchestrator=orch)

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            with patch("resume_ops_api.cli.build_container", return_value=container):
                result = await async_main(args)
                assert result == 1

    @pytest.mark.asyncio
    async def test_successful_generation_with_sections(self, tmp_path: Path) -> None:
        resume_path = tmp_path / "resume.json"
        resume_path.write_text('{"basics": {"name": "Test"}}')
        jd_path = tmp_path / "jd.md"
        jd_path.write_text("# JD")
        output_path = tmp_path / "output.pdf"
        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4\n")

        args = _make_namespace(
            resume=str(resume_path),
            jd=str(jd_path),
            output=str(output_path),
        )
        args.sections = "work,skills"

        orch = _FakeOrchestrator(pdf_path=str(fake_pdf))
        container = _FakeContainer(orchestrator=orch)

        with patch("resume_ops_api.cli.get_settings") as mock_get_settings:
            mock_settings = MagicMock()
            mock_settings.data_dir = tmp_path / "data"
            mock_get_settings.return_value = mock_settings

            with patch("resume_ops_api.cli.build_container", return_value=container):
                result = await async_main(args)
                assert result == 0
                assert output_path.is_file()

