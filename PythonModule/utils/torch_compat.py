"""Compatibility helpers for optional PyTorch features."""

import platform


def disable_unsupported_windows_compile(torch_module, system=None):
    """Make ``torch.compile`` an eager no-op on Windows.

    Some Transformers model modules apply ``@torch.compile`` while they are
    imported.  PyTorch versions that do not support Dynamo on Windows raise at
    that point, before the model can fall back to normal eager execution.
    """
    system = platform.system() if system is None else system
    compile_function = getattr(torch_module, "compile", None)
    if system.lower() != "windows" or compile_function is None:
        return False
    if getattr(compile_function, "_tcf_windows_eager_fallback", False):
        return False

    def eager_compile(model=None, *args, **kwargs):
        if model is None:
            return lambda target: target
        return model

    eager_compile._tcf_windows_eager_fallback = True
    torch_module.compile = eager_compile
    return True
