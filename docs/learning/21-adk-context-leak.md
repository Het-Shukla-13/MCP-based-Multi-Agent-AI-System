# 21 · ADK routing context leaking into replies (`fix/adk-context-leak`)

## Symptom (seen in a frontend screenshot)
A General Assistant reply ended with:
> For context: [root] called tool `transfer_to_agent` with parameters: {'agent_name': 'general'} … returned result: {'result': None}

## Cause, found by dumping what the model receives
A `before_model_callback` that prints `llm_request.contents` showed what ADK sends a sub-agent after delegation:
```
user: "Say hi"                                                      ← real message
user: "For context:" "[root] called tool `transfer_to_agent` …"     ← ADK bookkeeping
user: "For context:" "[root] `transfer_to_agent` tool returned …"   ← ADK bookkeeping
```
ADK rewrites other agents' events as **user** turns. The model treats them as things the user said and sometimes repeats them, especially for prompts like "repeat exactly…". It's intermittent, so a single clean run proves nothing.

## Rejected fix
`include_contents="none"` on sub-agents. Measured: the sub-agent then lost the **user's actual message** and answered about the tool call instead. Worse.

## Fix
`strip_routing_context` (a `before_model_callback` on every per-request sub-agent) removes only turns that start with "For context:" **and** mention `transfer_to_agent`. Everything else is untouched (other context, the real message, history in the system instruction). A callback returning `None` lets the edited request proceed.

**Lesson:** when a model output looks wrong, first look at the exact input the model received. Framework-generated input is input too.

Verified: unit test (bookkeeping removed, unrelated context kept) + 3 live runs through `RootAgent` with the "repeat exactly" prompt, with no leak. Tests: 35 passed.
