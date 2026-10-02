"""Application-layer file-editor implementations (DO-10).

The :class:`SandboxedFileEditor` lives in this package and is exported
through this module so consumers can write
``from simple_cli_coder_with_rag.application.file_editor import SandboxedFileEditor``.
"""

from __future__ import annotations

from simple_cli_coder_with_rag.application.file_editor.sandboxed_editor import (
    SandboxedFileEditor,
)

__all__ = ["SandboxedFileEditor"]
