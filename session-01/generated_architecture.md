# Session 1 — Architecture from the implementation

Based on `poem_bot.py` and the shared functions it calls in `../course-demos/common/llm.py`.

```mermaid
flowchart TD
    start["Run poem_bot.py as a script"] --> setup["Add course-demos to sys.path<br/>Import call_llm_safe from common.llm"]
    setup --> config["Shared helper loads dotenv configuration<br/>Existing environment takes precedence<br/>Then discovered .env, then course-demos/.env"]
    config --> main["main() chat loop<br/>Print greeting once"]
    main --> input["User input<br/>input() reads a natural-language message"]
    input --> |"EOFError or KeyboardInterrupt"| goodbye["Print goodbye and end loop"]
    input --> |"Message received"| exitclean["clean_message_text(message).lower()<br/>Trim and collapse whitespace; lowercase for exit check"]
    exitclean --> exitcheck{"exit, quit, or 退出?"}
    exitcheck --> |"Yes"| goodbye
    exitcheck --> |"No"| get["get_poetry_reply(message)<br/>Receives the original message"]
    get --> clean["clean_message_text()<br/>Trim and collapse whitespace"]
    clean --> empty{"Cleaned message empty?"}
    empty --> |"Yes"| reminder["Return request to enter a message<br/>No LLM call"]
    empty --> |"No"| prompt["Prompt construction<br/>Instruction plus cleaned message<br/>SYSTEM_PROMPT asks for meaning or emotion interpretation,<br/>one authentic classical Chinese poem line,<br/>and an optional short explanation"]
    prompt --> safe

    subgraph shared ["course-demos/common/llm.py"]
        safe["call_llm_safe()<br/>Receives system prompt, user prompt, and MOCK_REPLY"]
        safe --> llm_call["call_llm()"]
        llm_call --> provider{"llm_provider: first configured API key wins"}
        provider --> |"OpenAI, then Anthropic, then DeepSeek"| real["Real LLM API call<br/>Shared model, timeout, and retry settings"]
        provider --> |"No API key"| offline["Log mock diagnostic<br/>Return supplied MOCK_REPLY"]
        llm_call --> |"Any exception caught by call_llm_safe"| failure["Log failure diagnostic<br/>Return supplied MOCK_REPLY"]
        real --> |"Exception"| failure
        real --> |"Success"| result["Return model response text"]
    end

    offline --> mock["Mock fallback reply: fixed example for every message<br/>长风破浪会有时，直挂云帆济沧海。<br/>离线示例：愿这句诗给你继续前行的勇气。"]
    failure --> mock
    result --> reply["Final poetry reply returned by get_poetry_reply()"]
    mock --> reply
    reply --> display["main() prints returned text with 诗词： prefix"]
    reminder --> display
    display --> input
```

The model is asked to choose an appropriate authentic poem, but the code does not validate its response. Each call uses only the current message; the loop does not store conversation history. The mock is a fixed offline example, not an emotion-based selection.

## Differences from design.md

- The implementation has a repeating `main()` chat loop, exit commands, and EOF/keyboard-interrupt handling; the original diagram shows only a single input-to-reply flow.
- Cleaning happens twice for ordinary messages: once for the exit check and once inside `get_poetry_reply()`. Blank messages return a reminder without calling the LLM.
- `get_poetry_reply()` builds the user prompt and passes it with `SYSTEM_PROMPT` and the fixed `MOCK_REPLY` to the shared helper.
- `call_llm_safe()` wraps `call_llm()`. Missing keys trigger the mock inside `call_llm()`; exceptions trigger the wrapper's fallback.
- Provider selection checks configured keys in OpenAI → Anthropic → DeepSeek order, rather than testing actual API availability. Anthropic is not mentioned in the original configuration node.
- Configuration also includes the existing environment and a discovered `.env`. `.env.example` is a setup template, not a file read at runtime, so it is omitted from the generated flow.
- The poetry format and emotional relevance are prompt instructions, with no output validation. The offline reply always uses the same poem and explanation.
