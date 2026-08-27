from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio
import pytest
from pydantic import BaseModel

from resume_ops_api.core.config import Settings
from resume_ops_api.core.exceptions import AppError, ResumeValidationError
from resume_ops_api.services.llm import StructuredLLMClient
from resume_ops_api.services.renderer import ResumeRenderer
from resume_ops_api.services.schema import ResumeSchemaValidator
from resume_ops_api.services.themes import ThemeService


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


class TestResumeSchemaValidator:
    """Tests for ResumeSchemaValidator using the real JSON Resume schema."""

    @pytest.fixture
    def schema_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / "src" / "resume_ops_api" / "resources" / "resume_schema.json"

    @pytest.fixture
    def validator(self, schema_path: Path) -> ResumeSchemaValidator:
        return ResumeSchemaValidator(schema_path)

    def test_valid_minimal_resume_passes_validation(self, validator: ResumeSchemaValidator) -> None:
        """A minimal but type-correct payload passes validation."""
        minimal = {
            "basics": {
                "name": "John Doe",
                "email": "john@example.com",
            },
        }
        # Should not raise
        validator.validate(minimal, context="minimal resume")

    def test_valid_resume_with_work_array_passes(self, validator: ResumeSchemaValidator) -> None:
        """A fuller payload with work entries still passes."""
        payload = {
            "basics": {"name": "Jane", "email": "jane@example.com"},
            "work": [
                {"name": "Acme Corp", "position": "Engineer", "startDate": "2020-01-01"},
            ],
            "skills": [{"name": "Python"}],
        }
        validator.validate(payload, context="full resume")

    def test_basics_not_object_raises_validation_error(self, validator: ResumeSchemaValidator) -> None:
        with pytest.raises(ResumeValidationError) as exc_info:
            validator.validate({"basics": "not-an-object"}, context="bad basics")
        err = exc_info.value
        assert "failed JSON Resume schema validation" in err.message
        assert err.code == "resume_validation_failed"
        assert err.status_code == 422
        assert err.details["context"] == "bad basics"
        assert len(err.details["errors"]) >= 1
        error_paths = [e["path"] for e in err.details["errors"]]
        assert any("basics" in p for p in error_paths)

    def test_work_not_array_raises_validation_error(self, validator: ResumeSchemaValidator) -> None:
        with pytest.raises(ResumeValidationError) as exc_info:
            validator.validate({"basics": {"name": "T"}, "work": "not-array"}, context="bad work")
        error_paths = [e["path"] for e in exc_info.value.details["errors"]]
        assert any("work" in p for p in error_paths)

    def test_validation_error_includes_sorted_errors(self, validator: ResumeSchemaValidator) -> None:
        invalid = {
            "basics": "bad",
            "work": "also-bad",
        }
        with pytest.raises(ResumeValidationError) as exc_info:
            validator.validate(invalid, context="multi-error resume")
        paths = [e["path"] for e in exc_info.value.details["errors"]]
        # Errors are sorted by path — should be stable
        assert paths == sorted(paths)

    def test_custom_status_code_on_validation_error(self, validator: ResumeSchemaValidator) -> None:
        with pytest.raises(ResumeValidationError) as exc_info:
            validator.validate({"basics": "bad"}, context="custom status", status_code=400)
        assert exc_info.value.status_code == 400

    def test_validation_error_details_structure(self, validator: ResumeSchemaValidator) -> None:
        """Each error entry has 'path' and 'message' keys."""
        with pytest.raises(ResumeValidationError) as exc_info:
            validator.validate({"basics": "bad-type"}, context="structure test")
        for err_entry in exc_info.value.details["errors"]:
            assert "path" in err_entry
            assert "message" in err_entry

    def test_validate_with_nonexistent_schema_path(self, tmp_path: Path) -> None:
        bad_path = tmp_path / "nonexistent.json"
        with pytest.raises(FileNotFoundError):
            ResumeSchemaValidator(bad_path)

    def test_validate_with_invalid_json_schema(self, tmp_path: Path) -> None:
        bad_json = tmp_path / "bad_schema.json"
        bad_json.write_text("{invalid json")
        with pytest.raises(json.JSONDecodeError):
            ResumeSchemaValidator(bad_json)


# ---------------------------------------------------------------------------
# Theme service tests
# ---------------------------------------------------------------------------


class TestThemeService:
    """Tests for ThemeService allowlist validation and resolution."""

    @pytest.fixture
    def theme_service(self) -> ThemeService:
        return ThemeService(
            allowed_themes=["jsonresume-theme-stackoverflow", "jsonresume-theme-even"],
            default_theme="jsonresume-theme-stackoverflow",
        )

    def test_resolve_default_theme_when_candidate_is_none(self, theme_service: ThemeService) -> None:
        result = theme_service.resolve(None)
        assert result == "jsonresume-theme-stackoverflow"

    def test_resolve_default_theme_when_candidate_is_empty(self, theme_service: ThemeService) -> None:
        result = theme_service.resolve("")
        assert result == "jsonresume-theme-stackoverflow"

    def test_resolve_returns_trimmed_candidate(self, theme_service: ThemeService) -> None:
        result = theme_service.resolve("  jsonresume-theme-even  ")
        assert result == "jsonresume-theme-even"

    def test_resolve_raises_for_disallowed_theme(self, theme_service: ThemeService) -> None:
        with pytest.raises(AppError) as exc_info:
            theme_service.resolve("jsonresume-theme-onepage")
        assert exc_info.value.code == "invalid_theme"
        assert exc_info.value.status_code == 400
        assert "not allowed" in exc_info.value.message
        assert "allowed_themes" in exc_info.value.details

    def test_resolve_raises_for_unknown_theme_with_details(self, theme_service: ThemeService) -> None:
        with pytest.raises(AppError) as exc_info:
            theme_service.resolve("nonexistent-theme")
        assert exc_info.value.details["allowed_themes"] == [
            "jsonresume-theme-stackoverflow",
            "jsonresume-theme-even",
        ]

    def test_constructor_raises_when_default_not_in_allowed(self) -> None:
        with pytest.raises(AppError) as exc_info:
            ThemeService(
                allowed_themes=["jsonresume-theme-even"],
                default_theme="jsonresume-theme-stackoverflow",
            )
        assert exc_info.value.code == "invalid_theme_configuration"
        assert exc_info.value.status_code == 500
        assert "DEFAULT_THEME" in exc_info.value.message

    def test_single_allowed_theme_with_matching_default(self) -> None:
        svc = ThemeService(
            allowed_themes=["jsonresume-theme-stackoverflow"],
            default_theme="jsonresume-theme-stackoverflow",
        )
        assert svc.resolve(None) == "jsonresume-theme-stackoverflow"
        assert svc.resolve("jsonresume-theme-stackoverflow") == "jsonresume-theme-stackoverflow"


# ---------------------------------------------------------------------------
# LLM client tests
# ---------------------------------------------------------------------------


class TestStructuredLLMClient:
    """Tests for StructuredLLMClient using mocked completion functions."""

    class _FakeResponseModel(BaseModel):
        name: str
        value: int

    @pytest.mark.asyncio
    async def test_generate_structured_with_instructor_success(self) -> None:
        """When instructor returns the response model directly."""
        expected = self._FakeResponseModel(name="test", value=42)

        client = StructuredLLMClient(completion_fn=AsyncMock())
        with patch("resume_ops_api.services.llm.instructor.from_litellm") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=expected)
            mock_instructor.return_value = mock_client

            result = await client.generate_structured(
                model="openai/gpt-4o-mini",
                system_prompt="You are helpful.",
                user_prompt="Say hello.",
                response_model=self._FakeResponseModel,
            )

        assert result == expected
        assert result.name == "test"
        assert result.value == 42

    @pytest.mark.asyncio
    async def test_generate_structured_falls_back_to_json_parsing(self) -> None:
        """When instructor fails, falls back to raw JSON completion."""
        async def mock_completion(**kwargs):
            return {
                "choices": [
                    {"message": {"content": '{"name": "fallback", "value": 99}'}}
                ]
            }

        client = StructuredLLMClient(completion_fn=mock_completion)
        with patch("resume_ops_api.services.llm.instructor.from_litellm") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("instructor failed"))
            mock_instructor.return_value = mock_client

            result = await client.generate_structured(
                model="openai/gpt-4o-mini",
                system_prompt="You are helpful.",
                user_prompt="Say hello.",
                response_model=self._FakeResponseModel,
            )

        assert result.name == "fallback"
        assert result.value == 99

    @pytest.mark.asyncio
    async def test_generate_structured_raises_app_error_on_both_failures(self) -> None:
        """When both instructor and raw completion fail, raises AppError."""
        async def mock_completion(**kwargs):
            raise RuntimeError("raw completion also failed")

        client = StructuredLLMClient(completion_fn=mock_completion)
        with patch("resume_ops_api.services.llm.instructor.from_litellm") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("instructor failed"))
            mock_instructor.return_value = mock_client

            with pytest.raises(AppError) as exc_info:
                await client.generate_structured(
                    model="anthropic/claude-3-haiku",
                    system_prompt="You are helpful.",
                    user_prompt="Say hello.",
                    response_model=self._FakeResponseModel,
                )

        assert exc_info.value.code == "llm_generation_failed"
        assert exc_info.value.status_code == 502
        assert "anthropic/claude-3-haiku" in exc_info.value.message
        assert exc_info.value.details["model"] == "anthropic/claude-3-haiku"
        assert "raw completion also failed" in exc_info.value.details["error"]

    @pytest.mark.asyncio
    async def test_generate_structured_raises_when_fallback_json_is_invalid(self) -> None:
        """When the fallback JSON content is malformed."""
        async def mock_completion(**kwargs):
            return {
                "choices": [
                    {"message": {"content": "not valid json at all"}}
                ]
            }

        client = StructuredLLMClient(completion_fn=mock_completion)
        with patch("resume_ops_api.services.llm.instructor.from_litellm") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("instructor failed"))
            mock_instructor.return_value = mock_client

            with pytest.raises(AppError) as exc_info:
                await client.generate_structured(
                    model="openai/gpt-4o-mini",
                    system_prompt="You are helpful.",
                    user_prompt="Say hello.",
                    response_model=self._FakeResponseModel,
                )

        assert exc_info.value.code == "llm_generation_failed"
        assert exc_info.value.status_code == 502

    def test_default_completion_fn_is_set(self) -> None:
        client = StructuredLLMClient()
        # Should default to litellm.acompletion
        from litellm import acompletion

        assert client.completion_fn is acompletion

    @pytest.mark.asyncio
    async def test_generate_structured_retries_on_transient_error(self) -> None:
        """Verify that StructuredLLMClient retries on transient API/network errors."""
        call_count = 0
        async def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("API timeout error")
            return {
                "choices": [
                    {"message": {"content": '{"name": "retry-success", "value": 10}'}}
                ]
            }

        client = StructuredLLMClient(completion_fn=mock_completion)
        with patch("resume_ops_api.services.llm.instructor.from_litellm") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("instructor failed"))
            mock_instructor.return_value = mock_client
            
            # Patch wait to none so the retries run instantly
            from tenacity import wait_none
            with patch("tenacity.wait_exponential", return_value=wait_none()):
                result = await client.generate_structured(
                    model="openai/gpt-4o-mini",
                    system_prompt="You are helpful.",
                    user_prompt="Say hello.",
                    response_model=self._FakeResponseModel,
                )

        assert result.name == "retry-success"
        assert result.value == 10
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_generate_structured_does_not_retry_on_validation_error(self) -> None:
        """Verify that StructuredLLMClient does not retry on Pydantic validation errors."""
        call_count = 0
        async def mock_completion(**kwargs):
            nonlocal call_count
            call_count += 1
            # Return invalid json that fails schema validation
            return {
                "choices": [
                    {"message": {"content": '{"invalid_key": "schema"}'}}
                ]
            }

        client = StructuredLLMClient(completion_fn=mock_completion)
        with patch("resume_ops_api.services.llm.instructor.from_litellm") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("instructor failed"))
            mock_instructor.return_value = mock_client

            from tenacity import wait_none
            with patch("tenacity.wait_exponential", return_value=wait_none()):
                with pytest.raises(AppError):
                    await client.generate_structured(
                        model="openai/gpt-4o-mini",
                        system_prompt="You are helpful.",
                        user_prompt="Say hello.",
                        response_model=self._FakeResponseModel,
                    )

        # Should only execute once since validation failures shouldn't be retried
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_generate_structured_unwraps_list_and_markdown_in_fallback(self) -> None:
        """Verify that fallback parser handles list wraps and markdown code blocks."""
        async def mock_completion(**kwargs):
            return {
                "choices": [
                    {"message": {"content": "```json\n[{\n  \"name\": \"fallback-robust\",\n  \"value\": 42\n}]\n```"}}
                ]
            }

        client = StructuredLLMClient(completion_fn=mock_completion)
        with patch("resume_ops_api.services.llm.instructor.from_litellm") as mock_instructor:
            mock_client = MagicMock()
            # Force instructors to fail to trigger step 3 fallback
            mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("instructor failed"))
            mock_instructor.return_value = mock_client

            result = await client.generate_structured(
                model="openai/gpt-4o-mini",
                system_prompt="You are helpful.",
                user_prompt="Say hello.",
                response_model=self._FakeResponseModel,
            )

        assert result.name == "fallback-robust"
        assert result.value == 42

    @pytest.mark.asyncio
    async def test_generate_structured_caches_successful_response(self) -> None:
        """When caching is enabled, successful validation results are cached."""
        expected = self._FakeResponseModel(name="test", value=42)
        completion_fn = AsyncMock()
        client = StructuredLLMClient(completion_fn=completion_fn, enable_cache=True)
        
        with patch("resume_ops_api.services.llm.instructor.from_litellm") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=expected)
            mock_instructor.return_value = mock_client

            result1 = await client.generate_structured(
                model="openai/gpt-4o-mini",
                system_prompt="system",
                user_prompt="user",
                response_model=self._FakeResponseModel,
            )
            # The second call should hit the cache and not invoke completions
            result2 = await client.generate_structured(
                model="openai/gpt-4o-mini",
                system_prompt="system",
                user_prompt="user",
                response_model=self._FakeResponseModel,
            )

        assert result1 == expected
        assert result2 == expected
        assert mock_client.chat.completions.create.call_count == 1

    @pytest.mark.asyncio
    async def test_generate_structured_does_not_cache_validation_failure(self) -> None:
        """When validation fails, the result is not saved to the cache."""
        async def mock_completion(**kwargs):
            return {
                "choices": [
                    {"message": {"content": "not valid json"}}
                ]
            }

        client = StructuredLLMClient(completion_fn=mock_completion, enable_cache=True)
        with patch("resume_ops_api.services.llm.instructor.from_litellm") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("force fallback"))
            mock_instructor.return_value = mock_client

            # First run fails validation
            with pytest.raises(AppError):
                await client.generate_structured(
                    model="openai/gpt-4o-mini",
                    system_prompt="system",
                    user_prompt="user",
                    response_model=self._FakeResponseModel,
                )

        # Cache must remain empty
        assert len(client.cache) == 0



# ---------------------------------------------------------------------------
# Renderer tests
# ---------------------------------------------------------------------------


class TestResumeRenderer:
    """Tests for ResumeRenderer with mocked subprocess and file system."""

    @pytest.fixture
    def renderer(self) -> ResumeRenderer:
        return ResumeRenderer(binary="fake-resumed")

    def test_resolve_binary_uses_which_first(self, renderer: ResumeRenderer) -> None:
        with patch("resume_ops_api.services.renderer.shutil.which", return_value="/usr/local/bin/fake-resumed"):
            resolved = renderer._resolve_binary()
            assert resolved == "/usr/local/bin/fake-resumed"

    def test_resolve_binary_falls_back_to_local_npm(self, renderer: ResumeRenderer) -> None:
        with patch("resume_ops_api.services.renderer.shutil.which", return_value=None):
            with patch.object(Path, "exists", return_value=True):
                with patch.object(Path, "home", return_value=Path("/home/testuser")):
                    resolved = renderer._resolve_binary()
                    assert resolved == "/home/testuser/.npm-global/bin/fake-resumed"

    def test_resolve_binary_returns_original_when_not_found(self, renderer: ResumeRenderer) -> None:
        with patch("resume_ops_api.services.renderer.shutil.which", return_value=None):
            with patch.object(Path, "exists", return_value=False):
                resolved = renderer._resolve_binary()
                assert resolved == "fake-resumed"

    @pytest.mark.asyncio
    async def test_render_success(self, renderer: ResumeRenderer, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"

        async def mock_communicate():
            return b"", b""

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(side_effect=mock_communicate)

        with patch("resume_ops_api.services.renderer.shutil.which", return_value="/usr/bin/fake-resumed"):
            with patch("resume_ops_api.services.renderer.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)):
                # Pre-create a valid PDF in the expected output path so
                # the post-render header check passes
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "output.pdf").write_bytes(b"%PDF-1.4 fake")
                result = await renderer.render(
                    resume={"basics": {"name": "Test"}},
                    theme="jsonresume-theme-stackoverflow",
                    output_dir=output_dir,
                )

        assert result == output_dir / "output.pdf"
        assert (output_dir / "resume.json").exists()
        assert (output_dir / "output.pdf").exists()

    @pytest.mark.asyncio
    async def test_render_writes_resume_json(self, renderer: ResumeRenderer, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        resume_data = {"basics": {"name": "Jane Doe", "email": "jane@example.com"}}

        async def mock_communicate():
            return b"", b""

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(side_effect=mock_communicate)

        with patch("resume_ops_api.services.renderer.shutil.which", return_value="/usr/bin/fake-resumed"):
            with patch("resume_ops_api.services.renderer.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)):
                # Pre-create PDF header
                pdf_path = output_dir / "output.pdf"
                output_dir.mkdir(parents=True, exist_ok=True)
                pdf_path.write_bytes(b"%PDF-1.4 fake")

                await renderer.render(
                    resume=resume_data,
                    theme="jsonresume-theme-stackoverflow",
                    output_dir=output_dir,
                )

        written = json.loads((output_dir / "resume.json").read_text(encoding="utf-8"))
        assert written == resume_data

    @pytest.mark.asyncio
    async def test_render_raises_on_nonzero_returncode(self, renderer: ResumeRenderer, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"

        async def mock_communicate():
            return b"", b"rendering error: theme not found"

        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(side_effect=mock_communicate)

        with patch("resume_ops_api.services.renderer.shutil.which", return_value="/usr/bin/fake-resumed"):
            with patch("resume_ops_api.services.renderer.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)):
                with pytest.raises(AppError) as exc_info:
                    await renderer.render(
                        resume={"basics": {"name": "Test"}},
                        theme="jsonresume-theme-stackoverflow",
                        output_dir=output_dir,
                    )

        assert exc_info.value.code == "render_failed"
        assert exc_info.value.status_code == 500
        assert "rendering error" in exc_info.value.details["stderr"]

    @pytest.mark.asyncio
    async def test_render_raises_when_output_not_pdf(self, renderer: ResumeRenderer, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"

        async def mock_communicate():
            return b"", b""

        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(side_effect=mock_communicate)

        with patch("resume_ops_api.services.renderer.shutil.which", return_value="/usr/bin/fake-resumed"):
            with patch("resume_ops_api.services.renderer.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)):
                # Pre-create a file that is NOT a valid PDF
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "output.pdf").write_bytes(b"NOT A PDF FILE")
                with pytest.raises(AppError) as exc_info:
                    await renderer.render(
                        resume={"basics": {"name": "Test"}},
                        theme="jsonresume-theme-stackoverflow",
                        output_dir=output_dir,
                    )

        assert exc_info.value.code == "invalid_pdf_output"
        assert exc_info.value.status_code == 500
        assert "not a valid PDF" in exc_info.value.message


# ---------------------------------------------------------------------------
# Rate limiter and StructuredLLMClient concurrency/rate-limiting tests
# ---------------------------------------------------------------------------


class TestLLMRateLimiting:
    @pytest.mark.asyncio
    async def test_async_rate_limiter_throttling(self) -> None:
        """Verify that AsyncRateLimiter delays calls once the request limit is reached."""
        from resume_ops_api.services.llm import AsyncRateLimiter
        import time

        # Allow 2 requests per 0.1 seconds
        limiter = AsyncRateLimiter(requests=2, period=0.1)

        start = time.monotonic()
        await limiter.acquire()
        await limiter.acquire()
        duration_first_two = time.monotonic() - start

        # The first two should be acquired almost instantly
        assert duration_first_two < 0.05

        # The third one should trigger a sleep of around 0.1s
        await limiter.acquire()
        total_duration = time.monotonic() - start
        assert total_duration >= 0.09

    @pytest.mark.asyncio
    async def test_structured_llm_client_rate_limiting(self) -> None:
        """Verify that StructuredLLMClient throttles calls according to rate_limit_requests."""
        import time
        from unittest.mock import AsyncMock

        expected = TestStructuredLLMClient._FakeResponseModel(name="test", value=42)

        client = StructuredLLMClient(
            completion_fn=AsyncMock(),
            rate_limit_requests=2,
            rate_limit_period=0.1,
        )

        with patch("resume_ops_api.services.llm.instructor.from_litellm") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=expected)
            mock_instructor.return_value = mock_client

            start = time.monotonic()
            tasks = [
                client.generate_structured(
                    model="openai/gpt-4o-mini",
                    system_prompt="system",
                    user_prompt="user",
                    response_model=TestStructuredLLMClient._FakeResponseModel,
                )
                for _ in range(3)
            ]
            results = await asyncio.gather(*tasks)

        # All 3 calls should succeed
        assert len(results) == 3
        assert all(r == expected for r in results)

        # Since rate limit is 2 per 0.1s, the third call should be delayed, causing total time >= 0.1s
        total_time = time.monotonic() - start
        assert total_time >= 0.09

    @pytest.mark.asyncio
    async def test_structured_llm_client_concurrency(self) -> None:
        """Verify StructuredLLMClient respects max_concurrency limit."""
        import time
        from unittest.mock import AsyncMock

        expected = TestStructuredLLMClient._FakeResponseModel(name="test", value=42)
        active_calls = 0
        max_active_calls = 0
        lock = asyncio.Lock()

        async def mock_completion(**kwargs):
            nonlocal active_calls, max_active_calls
            async with lock:
                active_calls += 1
                if active_calls > max_active_calls:
                    max_active_calls = active_calls
            await asyncio.sleep(0.05)
            async with lock:
                active_calls -= 1
            return {
                "choices": [
                    {"message": {"content": '{"name": "test", "value": 42}'}}
                ]
            }

        client = StructuredLLMClient(
            completion_fn=mock_completion,
            max_concurrency=2,
        )

        # Force instructors to fail to go to step 3 raw completion
        with patch("resume_ops_api.services.llm.instructor.from_litellm") as mock_instructor:
            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("force fallback"))
            mock_instructor.return_value = mock_client

            tasks = [
                client.generate_structured(
                    model="openai/gpt-4o-mini",
                    system_prompt="system",
                    user_prompt="user",
                    response_model=TestStructuredLLMClient._FakeResponseModel,
                )
                for _ in range(4)
            ]
            results = await asyncio.gather(*tasks)

        assert len(results) == 4
        assert max_active_calls <= 2


class TestContainerInitialization:
    """Tests for the build_container helper and caching setup."""

    def test_build_container_enables_client_cache(self, tmp_path: Path) -> None:
        from resume_ops_api.services.container import build_container

        settings = Settings(
            _env_file=None,
            default_model="openai/gpt-4o-mini",
            data_dir=tmp_path,
            llm_cache=True,
        )

        with patch("resume_ops_api.services.container.Database"), \
             patch("resume_ops_api.services.container.ResumeSchemaValidator"), \
             patch("resume_ops_api.services.container.ThemeService"), \
             patch("resume_ops_api.services.container.ResumeRenderer"), \
             patch("resume_ops_api.services.container.CallbackService"), \
             patch("resume_ops_api.services.container.ResumeMerger"), \
             patch("resume_ops_api.services.container.ResumeGraph"), \
             patch("resume_ops_api.services.container.TailorOrchestrator"), \
             patch("resume_ops_api.services.container.JobStore"), \
             patch("resume_ops_api.services.container.AsyncJobRunner"):
            
            container = build_container(settings)

        assert container.llm_client.enable_cache is True


class TestAtsText:
    """Tests for ATS-friendly plain-text formatting (Label: value layout)."""

    def test_json_to_ats_text_format(self) -> None:
        from resume_ops_api.services.ats_text import json_to_ats_text

        resume_data = {
            "basics": {
                "name": "Jane Doe",
                "label": "Software Architect",
                "email": "jane@example.com",
                "phone": "+1-555-0199",
                "summary": "Experienced distributed systems architect.",
                "location": {"city": "San Francisco", "region": "CA", "countryCode": "US"},
            },
            "work": [
                {
                    "name": "Acme Corp",
                    "position": "Principal Engineer",
                    "startDate": "2020-01",
                    "endDate": "2023-05",
                    "summary": "Led architecture.",
                    "highlights": ["Scaled systems to 10M DAU", "Reduced latency by 40%"],
                }
            ],
            "skills": [
                {
                    "name": "Cloud & Backend",
                    "keywords": ["Python", "Go", "Kubernetes", "PostgreSQL"],
                }
            ],
        }

        ats_text = json_to_ats_text(resume_data)

        # Assert ATS format invariants: Label: value lines
        assert "Name: Jane Doe" in ats_text
        assert "Title: Software Architect" in ats_text
        assert "Email: jane@example.com" in ats_text
        assert "Phone: +1-555-0199" in ats_text
        assert "Location: San Francisco, CA, US" in ats_text
        assert "Company: Acme Corp" in ats_text
        assert "Job Title: Principal Engineer" in ats_text
        assert "From: January 2020" in ats_text
        assert "To: May 2023" in ats_text
        assert "Skill Category: Cloud & Backend" in ats_text
        assert "Keywords: Python, Go, Kubernetes, PostgreSQL" in ats_text
        assert "Scaled systems to 10M DAU" in ats_text


class TestResumeGraphPipeline:
    """Tests for the 4-node ResumeGraph execution and section skipping."""

    @pytest.mark.asyncio
    async def test_graph_executes_with_selective_sections(self, tmp_path: Path) -> None:
        from tests.conftest import FakeStructuredLLMClient, FakeRenderer
        from resume_ops_api.graph.pipeline import ResumeGraph
        from resume_ops_api.graph.merge import ResumeMerger
        from resume_ops_api.graph.state import ResumeGraphState

        schema_path = Path(__file__).resolve().parent.parent / "src" / "resume_ops_api" / "resources" / "resume_schema.json"
        validator = ResumeSchemaValidator(schema_path)
        sample_resume = {
            "basics": {"name": "Test Candidate", "label": "Original Title", "summary": "Original summary."},
            "work": [{"name": "Acme", "position": "Dev", "startDate": "2020-01-01", "summary": "Original work"}],
            "skills": [{"name": "Original Skill", "keywords": ["Legacy"]}],
            "projects": [{"name": "Original Project", "description": "Original proj"}],
        }

        client = FakeStructuredLLMClient(sample_resume)
        graph = ResumeGraph(
            llm_client=client,
            merger=ResumeMerger(),
            renderer=FakeRenderer(),
            validator=validator,
        )

        # Run with only "work" section enabled
        state: ResumeGraphState = {
            "original_resume": sample_resume,
            "job_description": "Looking for a Dev",
            "theme": "jsonresume-theme-stackoverflow",
            "job_id": "test-job-123",
            "output_dir": tmp_path,
            "sections": ["work"],
        }

        final_state = await graph.run(state)
        final_resume = final_state["final_resume"]

        # Work was tailored
        assert "Tailored" in final_resume["work"][0]["summary"]
        # Basics, skills, and projects preserved from original
        assert final_resume["basics"]["label"] == "Original Title"
        assert final_resume["basics"]["summary"] == "Original summary."
        assert final_resume["skills"][0]["name"] == "Original Skill"
        assert final_resume["projects"][0]["description"] == "Original proj"



