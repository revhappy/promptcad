"""PromptCAD distribution layer.

Everything in this package is added by the PromptCAD build and does not exist
in the upstream GPT4FreeCAD addon. It holds the things that are true of the
*product* rather than of the addon: the prompt-first window, and finding a
local model without making the user configure one.

Nothing in the upstream tree imports this package. The only wiring is a short
block appended to InitGui.py at build time, so upstream stays byte-identical
and this layer can be dropped without leaving a dangling reference.
"""
