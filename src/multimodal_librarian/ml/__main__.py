"""
Allow running ``python -m multimodal_librarian.ml`` as a convenience
entry point that prints available sub-commands.
"""

from __future__ import annotations

import sys


def main() -> None:
    print(
        "Medical Knowledge Fine-Tuning Pipeline\n"
        "\n"
        "Available commands:\n"
        "  python -m multimodal_librarian.ml.finetune\n"
        "      Fine-tune a model with QLoRA\n"
        "  python -m multimodal_librarian.ml.export\n"
        "      Export model to GGUF for Ollama\n"
        "  python -m multimodal_librarian.ml.evaluate\n"
        "      Evaluate base vs fine-tuned model\n"
        "\n"
        "Run any command with --help for usage details."
    )


if __name__ == "__main__":
    main()
    sys.exit(0)
