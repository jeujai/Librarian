"""
GGUF exporter for fine-tuned MLX models.

Merges LoRA adapter weights with the base model, converts to GGUF
format via llama.cpp, generates an Ollama Modelfile, and optionally
registers the model with a local Ollama instance.

Runs on the host machine (not inside Docker) alongside the QLoRA
trainer and evaluation runner.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .models import ExportConfig, ExportResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SYSTEM_PROMPT = (
    "You are a medical knowledge assistant trained on curated medical "
    "textbooks, clinical guidelines, and biomedical literature. Provide "
    "accurate, evidence-based responses to medical questions."
)

# Ollama Modelfile parameter defaults
_DEFAULT_TEMPERATURE = 0.7
_DEFAULT_TOP_P = 0.9
_DEFAULT_NUM_CTX = 4096
_DEFAULT_NUM_PREDICT = 512  # Cap response length to prevent repetition loops


# ---------------------------------------------------------------------------
# GGUFExporter
# ---------------------------------------------------------------------------


class GGUFExporter:
    """Export a fine-tuned MLX model to GGUF for Ollama deployment.

    The export pipeline:

    1. Fuse LoRA adapters with the base model via ``mlx_lm.fuse()``.
    2. Convert the fused model to GGUF via the llama.cpp
       ``convert_hf_to_gguf.py`` script.
    3. Quantize to the configured level (default Q4_K_M).
    4. Generate an Ollama Modelfile.
    5. Register with the local Ollama instance (if available).

    If Ollama is not running the GGUF file and Modelfile are saved to
    the output directory with instructions for manual registration.

    Args:
        config: An ``ExportConfig`` with adapter path, base model,
            output directory, model name, quantization level, and
            system prompt.
    """

    def __init__(self, config: ExportConfig) -> None:
        self.config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(self) -> ExportResult:
        """Run the full export pipeline.

        Returns:
            An ``ExportResult`` with paths, sizes, and registration
            status.

        Raises:
            FileNotFoundError: If the adapter path does not exist.
            RuntimeError: If fusing or GGUF conversion fails.
        """
        adapter_path = Path(self.config.adapter_path)
        output_dir = Path(self.config.output_dir)

        # Validate adapter path
        if not adapter_path.exists():
            raise FileNotFoundError(
                f"Adapter path not found: {adapter_path}. "
                f"Run fine-tuning first to produce LoRA adapters."
            )

        # Ensure output directory exists
        self._ensure_output_dir(output_dir)

        # Step 1: Fuse LoRA adapters with base model (Req 6.1)
        fused_model_dir = output_dir / "fused_model"
        self._fuse_adapters(adapter_path, fused_model_dir)

        # Step 2: Try GGUF conversion, fall back to safetensors import
        # Ollama 0.11+ can import safetensors models directly, so GGUF
        # conversion is optional. If the convert script isn't available
        # or fails, we use the fused safetensors directory instead.
        gguf_filename = f"{self.config.model_name}.gguf"
        gguf_path = output_dir / gguf_filename
        model_source = str(fused_model_dir)  # Default: safetensors

        try:
            self._convert_to_gguf(fused_model_dir, gguf_path)
            if gguf_path.exists():
                model_source = str(gguf_path)
        except (RuntimeError, Exception) as exc:
            logger.warning(
                "GGUF Export: GGUF conversion failed (%s). "
                "Using safetensors import via Ollama instead.",
                exc,
            )

        # Compute model file size
        gguf_size_mb = 0.0
        if gguf_path.exists():
            gguf_size_mb = round(
                gguf_path.stat().st_size / (1024 * 1024), 2
            )
        else:
            # Estimate from safetensors
            for f in fused_model_dir.glob("*.safetensors"):
                gguf_size_mb += round(
                    f.stat().st_size / (1024 * 1024), 2
                )

        # Step 3: Generate Ollama Modelfile (Req 6.3)
        modelfile_path = self._generate_modelfile(
            Path(model_source), self.config.model_name
        )

        # Step 5: Register with Ollama (Req 6.4, 6.5)
        ollama_registered = False
        manual_instructions: Optional[str] = None

        if self.config.register_ollama:
            ollama_registered = self._register_with_ollama(
                modelfile_path, self.config.model_name
            )
            if not ollama_registered:
                quantize_flag = self.config.quantization.lower()
                manual_instructions = (
                    f"Ollama is not running or unreachable. "
                    f"To register the model manually:\n"
                    f"  1. Start Ollama: ollama serve\n"
                    f"  2. Create the model: ollama create "
                    f"{self.config.model_name} "
                    f"-f {modelfile_path} "
                    f"--quantize {quantize_flag}\n"
                    f"  3. Test: ollama run "
                    f"{self.config.model_name} "
                    f'"What is metformin?"'
                )
                logger.info(
                    "GGUF Export: Ollama not available. "
                    "GGUF and Modelfile saved to %s. %s",
                    output_dir,
                    manual_instructions,
                )

        # Clean up fused model directory to save disk space
        # Only clean up if we successfully converted to GGUF
        if gguf_path.exists():
            self._cleanup_fused_model(fused_model_dir)

        result = ExportResult(
            gguf_path=str(gguf_path),
            modelfile_path=str(modelfile_path),
            model_name=self.config.model_name,
            gguf_size_mb=gguf_size_mb,
            quantization=self.config.quantization,
            ollama_registered=ollama_registered,
            manual_instructions=manual_instructions,
        )

        logger.info(
            "GGUF Export: Complete — gguf=%s (%.1f MB), "
            "quantization=%s, ollama_registered=%s",
            gguf_path,
            gguf_size_mb,
            self.config.quantization,
            ollama_registered,
        )

        return result

    # ------------------------------------------------------------------
    # Step 1: Fuse LoRA adapters (Requirement 6.1)
    # ------------------------------------------------------------------

    def _fuse_adapters(
        self,
        adapter_path: Path,
        fused_model_dir: Path,
    ) -> None:
        """Fuse LoRA adapter weights with the base model.

        Uses ``mlx_lm.fuse()`` to merge the trained LoRA adapters
        into the base model weights, producing a standalone model
        directory.

        Args:
            adapter_path: Path to the LoRA adapter weights.
            fused_model_dir: Output directory for the fused model.

        Raises:
            RuntimeError: If fusing fails.
        """
        logger.info(
            "GGUF Export: Fusing adapters from %s with base "
            "model %s",
            adapter_path,
            self.config.base_model,
        )

        try:
            fused_model_dir.mkdir(parents=True, exist_ok=True)
            # Use the mlx_lm CLI to fuse + dequantize, which properly
            # merges LoRA weights into the base model tensors.
            # The Python API (fuse_load + fuse_save) leaves LoRA layers
            # as separate linear.weight + lora_a + lora_b tensors,
            # which Ollama can't load.
            import subprocess as _sp
            cmd = [
                sys.executable, "-m", "mlx_lm", "fuse",
                "--model", self.config.base_model,
                "--adapter-path", str(adapter_path),
                "--save-path", str(fused_model_dir),
                "--dequantize",
            ]
            result = _sp.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(
                    f"mlx_lm fuse failed (exit {result.returncode}): "
                    f"{result.stderr}"
                )
            logger.info(
                "GGUF Export: Fused dequantized model saved to %s",
                fused_model_dir,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to fuse LoRA adapters with base model. "
                f"Verify that the adapter path '{adapter_path}' "
                f"contains valid LoRA weights compatible with "
                f"'{self.config.base_model}'. Error: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Step 2–3: Convert to GGUF (Requirement 6.2)
    # ------------------------------------------------------------------

    def _convert_to_gguf(
        self,
        fused_model_dir: Path,
        gguf_path: Path,
    ) -> None:
        """Convert the fused model to GGUF format.

        Uses the llama.cpp ``convert_hf_to_gguf.py`` script to
        convert the fused HuggingFace-format model to GGUF, then
        quantizes to the configured level (default Q4_K_M).

        Args:
            fused_model_dir: Path to the fused model directory.
            gguf_path: Output path for the GGUF file.

        Raises:
            RuntimeError: If conversion or quantization fails.
        """
        logger.info(
            "GGUF Export: Converting fused model to GGUF "
            "(%s quantization)",
            self.config.quantization,
        )

        # Locate the llama.cpp convert script
        convert_script = self._find_convert_script()

        # Step 2: Convert HF model to unquantized GGUF
        unquantized_path = gguf_path.with_suffix(".f16.gguf")
        self._run_convert_script(
            convert_script, fused_model_dir, unquantized_path
        )

        # Step 3: Quantize to target level
        self._quantize_gguf(unquantized_path, gguf_path)

        # Clean up unquantized intermediate file
        if unquantized_path.exists() and gguf_path.exists():
            unquantized_path.unlink()
            logger.info(
                "GGUF Export: Removed intermediate file %s",
                unquantized_path,
            )

    def _find_convert_script(self) -> str:
        """Locate the llama.cpp convert_hf_to_gguf.py script.

        Searches for the script in common locations:
        1. ``llama-cpp-python`` package installation
        2. System PATH (``convert_hf_to_gguf`` command)
        3. Common local build paths

        Returns:
            Path to the convert script or command name.

        Raises:
            RuntimeError: If the script cannot be found.
        """
        # Check if convert_hf_to_gguf is available as a command
        if shutil.which("convert_hf_to_gguf"):
            return "convert_hf_to_gguf"

        # Check if python -m llama_cpp works
        # (llama-cpp-python bundles conversion utilities)
        try:
            result = subprocess.run(
                ["python", "-c", "import llama_cpp"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                # Try to find the script in the package
                try:
                    import importlib.util

                    spec = importlib.util.find_spec("llama_cpp")
                    if spec and spec.origin:
                        pkg_dir = Path(spec.origin).parent
                        script = pkg_dir / "convert_hf_to_gguf.py"
                        if script.exists():
                            return str(script)
                except Exception:
                    pass
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # Check common local paths
        common_paths = [
            Path("scripts/convert_hf_to_gguf.py"),
            Path("llama.cpp/convert_hf_to_gguf.py"),
            Path.home() / "llama.cpp" / "convert_hf_to_gguf.py",
            Path("/usr/local/bin/convert_hf_to_gguf"),
        ]
        for path in common_paths:
            if path.exists():
                return str(path)

        raise RuntimeError(
            "Cannot find llama.cpp convert_hf_to_gguf script. "
            "Install llama-cpp-python (pip install llama-cpp-python) "
            "or clone llama.cpp and ensure convert_hf_to_gguf.py "
            "is on your PATH."
        )

    def _run_convert_script(
        self,
        convert_script: str,
        fused_model_dir: Path,
        output_path: Path,
    ) -> None:
        """Run the llama.cpp HF-to-GGUF conversion script.

        Args:
            convert_script: Path or command name for the script.
            fused_model_dir: Path to the fused model directory.
            output_path: Output path for the unquantized GGUF.

        Raises:
            RuntimeError: If conversion fails.
        """
        # Build command — if it's a .py file, run with python
        if convert_script.endswith(".py"):
            cmd = [
                "python",
                convert_script,
                str(fused_model_dir),
                "--outfile",
                str(output_path),
                "--outtype",
                "f16",
            ]
        else:
            cmd = [
                convert_script,
                str(fused_model_dir),
                "--outfile",
                str(output_path),
                "--outtype",
                "f16",
            ]

        logger.info(
            "GGUF Export: Running conversion: %s",
            " ".join(cmd),
        )

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"GGUF conversion failed (exit code "
                    f"{result.returncode}).\n"
                    f"Command: {' '.join(cmd)}\n"
                    f"stderr: {result.stderr.strip()}\n"
                    f"Ensure llama.cpp is properly installed "
                    f"and the fused model directory contains "
                    f"valid HuggingFace model files."
                )
            logger.info(
                "GGUF Export: Conversion complete → %s",
                output_path,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "GGUF conversion timed out after 10 minutes. "
                "This may indicate a very large model or system "
                "resource constraints."
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"Convert script not found: {convert_script}. "
                f"Install llama-cpp-python or ensure "
                f"convert_hf_to_gguf is on your PATH."
            )

    def _quantize_gguf(
        self,
        input_path: Path,
        output_path: Path,
    ) -> None:
        """Quantize a GGUF file to the configured level.

        Uses the ``llama-quantize`` command from llama.cpp.

        Args:
            input_path: Path to the unquantized GGUF file.
            output_path: Output path for the quantized GGUF.

        Raises:
            RuntimeError: If quantization fails.
        """
        quantize_cmd = self._find_quantize_command()

        cmd = [
            quantize_cmd,
            str(input_path),
            str(output_path),
            self.config.quantization,
        ]

        logger.info(
            "GGUF Export: Quantizing to %s: %s",
            self.config.quantization,
            " ".join(cmd),
        )

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"GGUF quantization failed (exit code "
                    f"{result.returncode}).\n"
                    f"Command: {' '.join(cmd)}\n"
                    f"stderr: {result.stderr.strip()}\n"
                    f"Ensure llama-quantize (from llama.cpp) "
                    f"is installed and on your PATH."
                )
            logger.info(
                "GGUF Export: Quantization complete → %s",
                output_path,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "GGUF quantization timed out after 10 minutes."
            )
        except FileNotFoundError:
            raise RuntimeError(
                f"Quantize command not found: {quantize_cmd}. "
                f"Install llama.cpp and ensure llama-quantize "
                f"is on your PATH."
            )

    def _find_quantize_command(self) -> str:
        """Locate the llama-quantize command.

        Returns:
            The command name or path.

        Raises:
            RuntimeError: If the command cannot be found.
        """
        # Check common command names
        for cmd_name in [
            "llama-quantize",
            "quantize",
            "llama_cpp_quantize",
        ]:
            if shutil.which(cmd_name):
                return cmd_name

        # Check common local paths
        common_paths = [
            Path("llama.cpp/build/bin/llama-quantize"),
            Path("llama.cpp/llama-quantize"),
            Path.home() / "llama.cpp" / "build" / "bin" / "llama-quantize",
        ]
        for path in common_paths:
            if path.exists():
                return str(path)

        raise RuntimeError(
            "Cannot find llama-quantize command. Build llama.cpp "
            "from source (https://github.com/ggerganov/llama.cpp) "
            "or install llama-cpp-python and ensure the quantize "
            "binary is on your PATH."
        )

    # ------------------------------------------------------------------
    # Step 4: Generate Modelfile (Requirement 6.3)
    # ------------------------------------------------------------------

    def _generate_modelfile(
        self,
        gguf_path: Path,
        model_name: str,
    ) -> Path:
        """Generate an Ollama Modelfile for the exported model.

        The Modelfile contains:
        - A ``FROM`` directive referencing the GGUF file path
        - ``PARAMETER`` directives for temperature, top_p, num_ctx
        - A ``SYSTEM`` directive with the medical assistant prompt

        Args:
            gguf_path: Path to the GGUF model file.
            model_name: Name for the Ollama model.

        Returns:
            Path to the generated Modelfile.
        """
        system_prompt = (
            self.config.system_prompt
            if self.config.system_prompt
            else _DEFAULT_SYSTEM_PROMPT
        )

        modelfile_content = (
            f"FROM {gguf_path.resolve()}\n"
            f"PARAMETER temperature {_DEFAULT_TEMPERATURE}\n"
            f"PARAMETER top_p {_DEFAULT_TOP_P}\n"
            f"PARAMETER num_ctx {_DEFAULT_NUM_CTX}\n"
            f"PARAMETER num_predict {_DEFAULT_NUM_PREDICT}\n"
            f"PARAMETER repeat_penalty 1.2\n"
            f'SYSTEM """{system_prompt}"""\n'
        )

        modelfile_path = gguf_path.parent / "Modelfile"
        modelfile_path.write_text(
            modelfile_content, encoding="utf-8"
        )

        logger.info(
            "GGUF Export: Modelfile generated at %s",
            modelfile_path,
        )

        return modelfile_path

    # ------------------------------------------------------------------
    # Step 5: Register with Ollama (Requirements 6.4, 6.5)
    # ------------------------------------------------------------------

    def _register_with_ollama(
        self,
        modelfile_path: Path,
        model_name: str,
    ) -> bool:
        """Register the model with the local Ollama instance.

        Runs ``ollama create <model_name> -f <modelfile_path>``.
        If Ollama is not running or unreachable, returns ``False``
        without raising an error (Requirement 6.5).

        Args:
            modelfile_path: Path to the Ollama Modelfile.
            model_name: Name to register the model under.

        Returns:
            ``True`` if registration succeeded, ``False`` otherwise.
        """
        if not self._is_ollama_available():
            logger.warning(
                "GGUF Export: Ollama is not running or "
                "unreachable. Skipping registration."
            )
            return False

        cmd = [
            "ollama",
            "create",
            model_name,
            "-f",
            str(modelfile_path),
            "--quantize",
            self.config.quantization.lower(),
        ]

        logger.info(
            "GGUF Export: Registering with Ollama: %s",
            " ".join(cmd),
        )

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout for model creation + quantization
            )
            if result.returncode == 0:
                logger.info(
                    "GGUF Export: Model '%s' registered with "
                    "Ollama successfully.",
                    model_name,
                )
                return True
            else:
                logger.warning(
                    "GGUF Export: Ollama registration failed "
                    "(exit code %d): %s",
                    result.returncode,
                    result.stderr.strip(),
                )
                return False
        except subprocess.TimeoutExpired:
            logger.warning(
                "GGUF Export: Ollama registration timed out "
                "after 5 minutes."
            )
            return False
        except FileNotFoundError:
            logger.warning(
                "GGUF Export: 'ollama' command not found. "
                "Install Ollama from https://ollama.ai"
            )
            return False

    @staticmethod
    def _is_ollama_available() -> bool:
        """Check whether the Ollama service is running.

        Runs ``ollama list`` as a lightweight connectivity check.

        Returns:
            ``True`` if Ollama responds, ``False`` otherwise.
        """
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (
            subprocess.TimeoutExpired,
            FileNotFoundError,
            OSError,
        ):
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_output_dir(output_dir: Path) -> None:
        """Create the output directory if it does not exist."""
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            if "No space left on device" in str(exc) or (
                hasattr(exc, "errno") and exc.errno == 28
            ):
                raise RuntimeError(
                    f"Cannot create output directory "
                    f"{output_dir}: no disk space available. "
                    f"Free up space and retry."
                ) from exc
            raise

    @staticmethod
    def _cleanup_fused_model(fused_model_dir: Path) -> None:
        """Remove the intermediate fused model directory.

        The fused model can be several GB. Once the GGUF file is
        produced we no longer need it.
        """
        if fused_model_dir.exists():
            try:
                shutil.rmtree(fused_model_dir)
                logger.info(
                    "GGUF Export: Cleaned up fused model "
                    "directory %s",
                    fused_model_dir,
                )
            except OSError as exc:
                logger.warning(
                    "GGUF Export: Could not remove fused model "
                    "directory %s: %s",
                    fused_model_dir,
                    exc,
                )
