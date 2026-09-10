"""Pure, deterministic domain logic shared by the workflow and the API.

Nothing in this package performs I/O, reads the clock, or generates randomness,
so it is safe to import inside Temporal workflow code and easy to unit test.
"""
