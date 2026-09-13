# Support float addition

`add()` rejects float arguments even though addition should support integers,
floats, and a mixture of the two. Preserve integer behavior and rejection of
string inputs.

This is an intentionally failing, trusted example. The scripted demonstration
uses a known replacement to validate tools. It is not an autonomous agent or an
evaluation benchmark. The original fixture must retain its bug.
