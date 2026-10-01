# Simple CLI code assistant with RAG
This is a simple lightweight python CLI application that uses [Anthropic SDK](https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python) to call on specific APIs, to create and interact with AI to create code. 
Is basically an OpenCode, but much simpler and with less functionality, the differential factor:
- It has build in RAG system that autopopulates from a command `/learn`
    - The command triggers a pipeline:
        - Compacts the session file into a JSON file, extracting the process/errors that can be infered from the session
        - The file then is chunked and then stored in a vectorial database.
The RAG system triggers on each request (This could cost a lot of time, so it needs to be optimized) and search if there's any error that matches with the request and retrieves it to the sesion to make sure the AI doesn't make the same mistakes.

## Delivery objectives
- The CLI works and the agents answer
- The command creates the JSON file
- The embedding model works
- The JSON file is stored into a vectorial database
- A prompt triggers semantic search and retrieves the important context (No reranking needed, simply extract few more closely related)
- The AI agent can edit files

The capacity from the AI to create and edit files in the device is the last capability to be created.

### Development objectives
- Follow a strict architecture and development design pattern
    - The selected architecture is a layers modular monolith. -> Combines both layered architecture and modular monolith, since the app runs fully from a single command, but internally folders are modular and clearly separated by layers that interact among themselves.
    - The design patterns selected were multiple and divided by "concern":
        **1. [Command](https://refactoring.guru/design-patterns/command)** (the main one)
        Each slash command (`/learn`, `/help`, `/clear`, ...) becomes an object with an `execute(context)` method, registered in a dictionary keyed by name. The CLI loop parses `/something`, looks it up, and runs it. Adding a command never touches the loop, which is the exact extensibility you'll want.

        **2. [Facade](https://refactoring.guru/design-patterns/facade)** (fits the layered architecture)
        Create a single `KnowledgeService` (or `RagFacade`) that the CLI/application layer talks to, exposing just two methods: `learn(session)` and `recall(request)`. Behind it sit the compactor, chunker, embedder, and vector DB. The upper layer never knows how many steps are involved, and each module stays independently replaceable.

        **3. [Strategy](https://refactoring.guru/design-patterns/strategy)**
        Use it wherever you have "one job, several possible implementations": the chunker (fixed-size vs. semantic), the embedder (local vs. API), and the vector store (Chroma, FAISS, SQLite-vec). Define a small interface for each and inject the chosen implementation. This also gives you cheap experimentation, which matters since RAG quality is mostly tuning.

        **4. [Decorator](https://refactoring.guru/design-patterns/decorator)** (The latency problem)
        Wrap the retriever to layer in optimizations without touching its core logic:
        `Retriever` → `CachedRetriever` → `TimeoutRetriever`.
        The cache skips repeat lookups, and the timeout falls back to "no memories" if the search takes too long, so RAG never blocks the user. (A caching/lazy-loading **Proxy** is a close alternative; Decorator is the more flexible fit here.)

#### Pattern designs Worth a mention in the application
[Adapter](https://refactoring.guru/design-patterns/adapter) — Wraping the Anthropic SDK behind your own `LLMClient` interface. It's a thin layer, but it isolates the vendor, makes testing with a fake client trivial, and keeps your core independent of the SDK, which suits layered architecture. — Fits with scalability concerns for allowing more APIs providers with OpenAI compatibility later.

[Chain of Responsibility](https://refactoring.guru/design-patterns/chain-of-responsibility) — The `/learn` pipeline `Compact → chunk → embed → store` is a sequence of stages. a plain ordered list of stage functions `for stage in stages: data = stage(data)`, that is similar to the Chain of Responsability were each step manages it's own process and the output is received by the next one. A formalization isn't required but it should be nice to bear in mind, to allow scalability. 

> All the before mentioned architecture and pattern designs must be documented (Already the mention to be included are explicit) inside the code and be followed, the design patterns specially must be easy to track and interpret from the folder and code structure. 


### Latency tips beyond patterns
- Skip retrieval when the request is trivial (a cheap length/keyword gate).
- Use a local embedding model and keep it loaded in memory.
- Set a similarity threshold plus a small top-k (3 or so), so you inject only strong matches.
- Run retrieval concurrently while you prepare the rest of the request.

## Suggested layering
| Layer | Patterns |
|---|---|
| Presentation (CLI) | Command registry |
| Application | Facade (`KnowledgeService`) |
| Domain/Infra | Strategy (chunker/embedder/store), Decorator (cache/timeout), Adapter (Claude SDK) |

If you must cut scope further, keep **Command + Facade + Strategy** and add Decorator once you actually measure the latency.