PromptCAD models
================

Drop a .gguf model file in this folder and PromptCAD will use it the next time
it starts. You do not have to change any settings.

You do not have to use this folder either. PromptCAD also looks in:

  * your Downloads folder
  * %APPDATA%\PromptCAD\<version>\models
  * your LM Studio models folder, if you have LM Studio
  * %USERPROFILE%\.machine\models

So the simplest path is: download a model from the link below in your browser
and start PromptCAD. It will find it in Downloads and say so in the Report
view.


Which model?
------------

  https://alphaintellabs.com/promptcad

The recommended starting point is NVIDIA Nemotron 3 Nano 4B (Q4_K_M, 2.84 GB).
It runs on a laptop CPU and it is the model PromptCAD's prompts are tuned
against.

Gemma 4 12B (Q4_K_M, 7.66 GB) is noticeably better at multi-step geometry but
wants 16 GB of RAM or a real GPU.

A partly downloaded file is ignored on purpose - PromptCAD checks the size and
skips anything still in flight, because a truncated .gguf fails deep inside the
inference engine with an error that makes no sense.


No model at all?
----------------

PromptCAD works without one. Add an API key for Anthropic, OpenAI, Google or
OpenRouter in Settings and it will use that instead. Local models are for
working offline and keeping your geometry on your own machine.
