# CLI selector boundary

The authoritative implementation is `text_category_profiler/cli/selector.py`.
The previous `text_category_profiler/selector.py` remains an import-compatible
module re-exporting the same `OptionSelector`, `MultiOptionSelector` and
`InteractiveOptionSelector` classes, plus `Fore`, `Back`, and `Style`.

The implementation was copied byte-for-byte from the original Git blob
`136a4caea6f9ad7858d9ca15cbe7c6308a60165a`. This relocation does
**not** change CLI prompts, default-option behavior, invalid-input retries,
mutable default arguments, or the explicit `curses` workflow. Such changes
require a separate behavior-reviewed PR.

Importing the module still requires the historical `colorama` dependency
but does not call `input()` or start a curses screen. `curses` is only
imported inside `InteractiveOptionSelector.proc()`; on platforms without
`curses`, it is not promised to work. No full Windows terminal session was
tested here.

Run isolated tests without real terminal I/O:
`python -m unittest -v tests.test_cli_selector_boundary`.
