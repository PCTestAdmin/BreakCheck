# Contributing to BreakCheck

Please open an issue with a minimal example, expected impact, actual result, OS, and Python version. Remove personal paths and confidential data before sharing reports or sample documents.

Keep new adapters read-only and bounded. Avoid executing embedded code or following untrusted remote references. Add unit tests for both detected references and false positives, and document limitations in the README. Run `python -m unittest discover -s tests -v` before submitting a pull request.
