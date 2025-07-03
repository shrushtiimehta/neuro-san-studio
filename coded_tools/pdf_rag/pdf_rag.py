"""Tool module for doing RAG from a pdf file"""

# Copyright (C) 2023-2025 Cognizant Digital Business, Evolutionary AI.
# All Rights Reserved.
# Issued under the Academic Public License.
#
# You can be released from the terms, and requirements of the Academic Public
# License by purchasing a commercial license.
# Purchase of a commercial license is mandatory for any use of the
# neuro-san-studio SDK Software in commercial settings.
#
# END COPYRIGHT

import os
import re
from typing import Any
from typing import Dict
from typing import List

from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community.vectorstores import InMemoryVectorStore
from langchain_core.documents import Document
from langchain_core.vectorstores.base import VectorStoreRetriever
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from neuro_san.interfaces.coded_tool import CodedTool

INVALID_PATH_PATTERN = r"[<>:\"|?*\x00-\x1F]"


class PdfRag(CodedTool):
    """
    CodedTool implementation which provides a way to do RAG on pdf files
    """

    def __init__(self):
        self.save_vector_store: bool = False
        self.abs_vector_store_path: str = None

    async def async_invoke(self, args: Dict[str, Any], sly_data: Dict[str, Any]) -> str:
        """
        Load a PDF from URL, build a vector store, and run a query against it.

        :param args: Dictionary containing:
          "query": search string
          "urls": list of pdf files
          "save_vector_store": save to JSON file if True
          "vector_store_path": relative path to this file

        :param sly_data: A dictionary whose keys are defined by the agent
            hierarchy, but whose values are meant to be kept out of the
            chat stream.

            This dictionary is largely to be treated as read-only.
            It is possible to add key/value pairs to this dict that do not
            yet exist as a bulletin board, as long as the responsibility
            for which coded_tool publishes new entries is well understood
            by the agent chain implementation and the coded_tool implementation
            adding the data is not invoke()-ed more than once.

            Keys expected for this implementation are:
                None
        :return: Text result from querying the built vector store,
            or error message
        """
        # Extract arguments from the input dictionary
        query: str = args.get("query", "")
        urls: List[str] = args.get("urls", [])

        # Save the generated vector store as a JSON file if True
        self.save_vector_store = args.get("save_vector_store", False)

        vector_store_path: str = args.get("vector_store_path", "")

        if vector_store_path:
            # Check for obviously invalid characters in filenames (basic check)
            if re.search(INVALID_PATH_PATTERN, vector_store_path):
                raise ValueError(f"Invalid vector_store_path: '{vector_store_path}'")

            # Check file extension
            if not vector_store_path.endswith(".json"):
                raise ValueError(f"vector_store_path must be a .json file, got: '{vector_store_path}'")

            if os.path.isabs(vector_store_path):
                # It's already an absolute path — use it directly
                self.abs_vector_store_path = vector_store_path
            else:
                # Combine to relative path to base path to make absolute path
                base_path: str = os.path.dirname(__file__)
                self.abs_vector_store_path = os.path.abspath(os.path.join(base_path, vector_store_path))

        # Validate presence of required inputs
        if not query:
            return "Error: No query provided."
        if not urls:
            return "Error: No urls provided"

        # Build the vector store and run the query
        vectorstore: InMemoryVectorStore = await self.generate_vector_store(urls)
        return await self.query_vectorstore(vectorstore, query)

    async def generate_vector_store(self, urls: List[str]) -> InMemoryVectorStore:
        """
        Asynchronously loads web documents from given URLs, split them into
        chunks, and build an in-memory vector store using OpenAI embeddings
        or load vectorstore if it is available.

        :param urls: List of URLs to fetch and embed
        :return: In-memory vector store containing the embedded document chunks
        """

        # If vector store file path is provided (abs_vector_store_path is not None), try to load vector store first.
        if self.abs_vector_store_path:
            try:
                vectorstore = InMemoryVectorStore.load(path=self.abs_vector_store_path, embedding=OpenAIEmbeddings())
                print(f"Loaded vector store from: {self.abs_vector_store_path}")
                return vectorstore
            except FileNotFoundError:
                print(f"Vector store not found. Creating from PDF: {urls}")

        docs: List[Document] = []
        for url in urls:
            try:
                loader = PyMuPDFLoader(file_path=url)
                doc: List[Document] = await loader.aload()
                docs.extend(doc)
                print(f"Successfully load pdf file from {url}")
            except FileNotFoundError:
                print(f"File not found: {url}")
            except ValueError as e:
                print(f"Invalid file path or unsupported input: {url} – {e}")

        # Split documents into smaller chunks for better embedding and
        # retrieval
        text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=100, chunk_overlap=50)
        doc_chunks: List[Document] = text_splitter.split_documents(docs)

        # Create an in-memory vector store with embeddings
        vectorstore: InMemoryVectorStore = await InMemoryVectorStore.afrom_documents(
            documents=doc_chunks,
            collection_name="rag-in-memory",
            embedding=OpenAIEmbeddings(),
        )

        if self.save_vector_store and self.abs_vector_store_path:
            os.makedirs(os.path.dirname(self.abs_vector_store_path), exist_ok=True)
            vectorstore.dump(path=self.abs_vector_store_path)
            print(f"Vector store saved to: {self.abs_vector_store_path}")

        return vectorstore

    async def query_vectorstore(self, vectorstore: InMemoryVectorStore, query: str) -> str:
        """
        Query the given vector store using the provided query string
        and return the combined content of retrieved documents.

        :param vectorstore: The in-memory vector store to query
        :param query: The user query to search for relevant documents
        :return: Concatenated text content of the retrieved documents
        """
        # Create a retriever interface from the vector store
        retriever: VectorStoreRetriever = vectorstore.as_retriever()

        # Perform an asynchronous similarity search
        results: List[Document] = await retriever.ainvoke(query)

        if results:
            print("Retrieval completed!")

        # Concatenate the content of all retrieved documents
        return "\n\n".join(doc.page_content for doc in results)
