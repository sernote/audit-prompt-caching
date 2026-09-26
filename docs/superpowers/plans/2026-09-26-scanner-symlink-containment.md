# Scanner symlink containment

## Goal

Prevent `extract_llm_calls.py` from reading files outside the selected scan root through file or directory symlinks, while preserving ordinary recursive source scanning and the JSON contract.

## Steps

1. Add a focused regression test for allowed-name symlinks to outside files and excluded `.env` content, plus an ordinary nested-file control. Confirm the test fails on the current scanner.
2. Reject symlinked files and use descriptor-based, no-follow reads during recursive traversal where supported. Keep a portable fallback that validates the file before reading.
3. Run the focused test, then ask an independent reviewer to challenge the patch for bypasses and regressions. Apply any needed correction.
4. Run the full unittest suite, package validator, trigger eval, syntax check, and whitespace/bytecode checks before reporting the fix.

## Package budget

The package guard measures all deferred skill files, including scripts. After rebasing on the latest `main`, the secured file-opening path raises the measured estimate from 77,687 to 78,447 tokens; update the test ceiling to that measured value after verification.
