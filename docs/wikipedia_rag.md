# Wikipedia RAG Assistant

The **Wikipedia RAG Assistant** answers user queries using Retrieval-Augmented Generation (RAG) over Wikipedia articles.

---

## File

[wikipedia_rag.hocon](../../registries/wikipedia_rag.hocon)

---

## Prerequisites for RAG:

This agent is **disabled by default**. To enable and use it:

1. Enable hocon file:
   
   ```hocon
   "wikipedia_rag.hocon": true
   ```
2. Installing the required package:

   ```bash
    pip install wikipedia asyncpg
    ```
   
## Prerequisites for PostgreSQL Vector Store

* Install Docker: https://www.docker.com/get-started/
* Install Python package:

    ```bash
    pip install langchain-postgres
    ```

* Set environment variables: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`
* Run docker container:

    ```bash
    docker run --name pgvector-container -e POSTGRES_USER=<user> -e POSTGRES_PASSWORD=<password> -e POSTGRES_DB=<db_name> -p 6024:5432 -d pgvector/pgvector:pg16
    ```
    
This starts and run a PostgreSQL container in the backgroud and maps port 6024 on your machine to port 5432 in the container.

---

## Example Conversation

### Human

```text
Compare ResNet, DenseNet, and EfficientNet for image classification.
```

### AI (Wikipedia RAG Assistant)

```text
Here is a comparison of ResNet, DenseNet, and EfficientNet for image classification:

- **ResNet (Residual Networks):** Known for its innovative use of skip connections or residual blocks,
ResNet allows models to be much deeper by mitigating the vanishing gradient problem that deep networks
face. It was a breakthrough in the ImageNet competition and remains a widely used architecture for
image classification tasks.

- **DenseNet:** This network architecture connects each layer to every other layer in a feed-forward
fashion. While traditional convolutional networks with L layers have L connections (one between each
layer and the next), DenseNet has L(L+1)/2 direct connections. This design improves the flow of
information and gradients throughout the network, making it very effective for image classification
tasks.

- **EfficientNet:** Introduced by Google AI in 2019, EfficientNet uses a new scaling method that
uniformly scales all dimensions of depth, width, and resolution using a compound coefficient. This
model is known for achieving better accuracy and efficiency than previous models and is widely used
in various computer vision tasks, including image classification, object detection, and segmentation.

Each of these models has unique strengths and innovations that contribute to their effectiveness in
image classification tasks.
```

---

## Architecture Overview

### Frontman Agent: **Wikipedia RAG Assistant**

* Serves as the **entry point** for user queries.  
* Parses the query to identify **key Wikipedia topics** for article retrieval (`wiki_queries`).  
* Passes both the **original query** and **topic list** to the `rag_retriever` tool.  
* Aggregates and composes the final answer.

### Tool: `rag_retriever`

* Loads Wikipedia pages for the given topics.
* Builds an **in-memory vector store** of the page text.  
* Performs semantic search and context retrieval to answer the user’s query.

#### User-Defined Arguments

##### Required

- `query` (str): The user’s question.  
- `wiki_queries` (list of str): Topics to load from Wikipedia, extracted from the query.

##### Optional

- `vector_store_type` (str): "in_memory" or "postgres" (default: "in_memory").
- `table_name` (str): Postgres table name. If the table exists, vectors are loaded from it instead of re-ingesting documents (default: "vectorstore").
- `lang` (str): Wikipedia language edition (default: `"en"`).  
- `load_max_docs` (int): Maximum number of Wikipedia pages to load per topic.  
- `doc_content_chars_max` (int): Max characters of text to keep per page (truncates for efficiency).  
- `save_vector_store` (bool): Persist the vector store to a .json file — in-memory mode only. Ignored in Postgres mode.
    - true → faster follow-ups on the same PDFs (single-topic reuse).
    - false → better for multi-topic runs (rebuilds each time).
- `vector_store_path` (str): Path to JSON store amd must end with .json. Used only when vector_store_type="in_memory" and save_vector_store=true.

---

## Debugging Hints

When troubleshooting, check the following:

- Confirm that the topics in wiki_queries exist on Wikipedia in the selected lang.
- Verify that load_max_docs and doc_content_chars_max are set to values that don’t cause timeouts or memory issues or do not lose a lot of context.
- If using save_vector_store: true, confirm that vector_store_path ends in .json and you query information only about very similar topics.
- If using vector_store_type: "postgres", confirm database connection details and table name are correct.
- Look at logs to ensure smooth vector store creation, document parsing, and query execution.
