# Session 1 - Poem Chatbot

## Goal

Build a chatbot that understands the meaning of a user's message and responds with an appropriate line of classical Chinese poetry.

## Architecture

```mermaid
flowchart TD

    user["User Input<br/>Natural language message"]
        --> entry["poem_bot.py<br/>Chatbot entry point"]

    entry --> clean["clean_message_text()<br/>Clean user input"]

    clean --> prompt["Prompt Construction<br/>Understand meaning and choose a suitable poem line"]

    prompt --> llm["course-demos/common/llm.py<br/>call_llm_safe()"]

    env["course-demos/.env<br/>OPENAI_API_KEY / DEEPSEEK_API_KEY"]
        --> llm

    example["course-demos/.env.example<br/>Configuration template"]
        --> env

    llm --> provider{"Is a real LLM available?"}

    provider -- "Yes" --> real["Real LLM<br/>Generate an appropriate poetry response"]

    provider -- "No or API failure" --> mock["Mock Fallback<br/>Return a deterministic poetry example"]

    real --> reply["Poetry Reply<br/>One classical Chinese poem line<br/>Optional short explanation"]

    mock --> reply