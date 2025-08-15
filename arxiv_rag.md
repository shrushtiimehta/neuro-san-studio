# ArXiv RAG Assistant

The **ArXiv RAG Assistant** answers user queries using Retrieval-Augmented Generation (RAG) over academic papers from [arXiv.org](https://arxiv.org).

---

## File

[arxiv_rag.hocon](../../registries/arxiv_rag.hocon)

---

## Example Conversation

### Human

```text
Write a literature review on diffusion models for generative modeling, comparing them with GANs, VAEs,
and energy-based models.
```

### AI (ArXiv RAG Assistant)

```text
The exploration of neural network architectures for image classification has led to the development
of models such as ResNet, DenseNet, and EfficientNet, each offering unique design philosophies and
performance characteristics.

### ResNet: Residual Networks
ResNet, introduced by He et al. (2015), revolutionized deep learning by addressing the vanishing
gradient problem through the introduction of residual connections. These connections allow gradients
to flow more easily through the network by skipping one or more layers, effectively enabling the
training of much deeper architectures. The fundamental building block of ResNet is the residual block,
which can be mathematically expressed as:

\[ \mathbf{y} = \mathcal{F}(\mathbf{x}, \{W_i\}) + \mathbf{x} \]

where \(\mathcal{F}\) denotes the residual mapping to be learned. The identity shortcut connection
(\(\mathbf{x}\)) allows the network to learn the residual mapping \(\mathcal{F}\), rather than the
complete transformation. ResNet architectures, such as ResNet-50, ResNet-101, and ResNet-152, have
demonstrated significant improvements in terms of depth and accuracy on datasets like ImageNet.

### DenseNet: Densely Connected Networks
DenseNet, proposed by Huang et al. (2017), introduced a dense connectivity pattern where each layer
receives input from all preceding layers. This connectivity is captured by concatenating feature maps
from previous layers, which can be formulated as:

\[ \mathbf{x}_l = H_l([\mathbf{x}_0, \mathbf{x}_1, \ldots, \mathbf{x}_{l-1}]) \]

where \([\mathbf{x}_0, \mathbf{x}_1, \ldots, \mathbf{x}_{l-1}]\) denotes the concatenation of feature
maps from layers \(0\) to \(l-1\). DenseNet efficiently utilizes parameters by promoting feature reuse
and reducing the necessity for redundant feature extraction. This results in a reduction of the number
of parameters compared to traditional architectures at equivalent depths, leading to improved parameter
efficiency and potentially reduced overfitting on smaller datasets.

### EfficientNet: Scaling Principles
EfficientNet, developed by Tan and Le (2019), introduces a novel compound scaling method that uniformly
scales network width, depth, and resolution using a set of fixed scaling coefficients. This approach
ensures a balanced scaling of all dimensions, optimizing both performance and efficiency. EfficientNet
models are denoted from B0 to B7, with each successive model larger and more capable. The core innovation
of EfficientNet is the MBConv block, derived from mobile inverted bottleneck convolution, which combines
depthwise separable convolutions with expansion layers to enhance efficiency.

### Comparative Analysis
- **Performance:** ResNet is known for its robustness and ability to train extremely deep networks,
achieving high accuracy on large datasets. DenseNet offers superior parameter efficiency, often achieving
comparable accuracy with fewer parameters. EfficientNet, through its scaling principles, provides an
optimal balance between accuracy and efficiency, often achieving state-of-the-art results with smaller
models.
- **Complexity:** ResNet introduces additional computational overhead due to identity mappings but remains
relatively efficient given its depth. DenseNet’s dense connections can lead to increased memory usage,
though it minimizes parameter count through feature reuse. EfficientNet achieves computational efficiency
through optimized architecture scaling.
- **Scalability:** EfficientNet’s compound scaling makes it highly scalable across different resource
constraints, from mobile devices to large-scale server environments. ResNet and DenseNet offer scalability
through their respective architectural designs but lack the systematic scaling methodology of EfficientNet.

In summary, each architecture offers unique advantages and trade-offs, making them suitable for different
contexts and applications in image classification. Researchers and practitioners must weigh these factors
based on the specific requirements of their tasks, resource constraints, and performance goals.
```

---

## Architecture Overview

### Frontman Agent: **ArXiv RAG Assistant**

* Serves as the **entry point** for user queries.  
* Parses the query to identify **key arXiv search terms** for paper retrieval (`arxiv_queries`).  
* Passes both the **original query** and **search terms** to the `rag_retriever` tool.  
* Aggregates and composes a technical answer to the user query.

### Tool: `rag_retriever`

* Find relevant research papers based on the given search terms.  
* Load the entire papers into an **in-memory vector store**.  
* Performs semantic search and context retrieval to answer the user’s query.

#### User-Defined Arguments

##### Optional

- `load_max_docs` (int): Maximum number of research pages to load per topic.  
- `doc_content_chars_max` (int): Max characters of text to keep per paper (truncates for efficiency).  
- `save_vector_store` (bool): Saves the vector store to a .json file.
    - true → faster follow-ups on the same topics (single-topic reuse).
    - false → better for multi-topic runs (rebuilds each time).
- `vector_store_path` (str): Path to JSON store amd must end with .json. Used only when save_vector_store=true.

---

## Debugging Hints

When troubleshooting, check the following:

- Ensure that the user queries are detailed with context.
- Verify that load_max_docs and doc_content_chars_max are set appropriately to avoid excessive memory use or context truncation.
- If using save_vector_store: true, confirm that vector_store_path ends in .json and you query information only about very similar topics.
- Look at logs to ensure smooth delegation across tool calls and proper response integration.
