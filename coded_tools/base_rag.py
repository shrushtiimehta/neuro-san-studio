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
from abc import ABC, abstractmethod
from typing import Any, List, Optional
import logging

from langchain_community.vectorstores import InMemoryVectorStore
from langchain_core.documents import Document
from langchain_core.vectorstores.base import VectorStoreRetriever
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Invalid file path character pattern
INVALID_PATH_PATTERN = r"[<>:\"|?*\x00-\x1F]"

logger = logging.getLogger(__name__)

class BaseRag(ABC):
    """
    Abstract Base Class for different types of RAG implementations.
    """

    def __init__(self):
        # Save the generated vector store as a JSON file if True
        self.save_vector_store: bool = False
        self.abs_vector_store_path: Optional[str] = None

    @abstractmethod
    async def load_documents(self, loader_args: Any) -> List[Document]:
        """
        Abstract method to load documents from a specific data source.
        """
        raise NotImplementedError
    
    def configure_vector_store_path(self, vector_store_path: Optional[str]):
        """
        Validate the vector store file path and set it as an absolute path.

        :param vector_store_path: Relative or absolute path to the vector store JSON file.
        :raises ValueError: If the path contains invalid characters or has an incorrect file extension.
        """
        if not vector_store_path:
            return

        # Check for obviously invalid characters in filenames (basic check)
        if re.search(INVALID_PATH_PATTERN, vector_store_path):
            logger.error("Invalid characters in vector_store_path: '%s'", vector_store_path)
            raise ValueError(f"Invalid vector_store_path: '{vector_store_path}'")

        # Check file extension
        if not vector_store_path.endswith(".json"):
            logger.error("vector_store_path must be a .json file, got: '%s'", vector_store_path)
            raise ValueError(f"vector_store_path must be a .json file, got: '{vector_store_path}'")


        if os.path.isabs(vector_store_path):
            # It's already an absolute path — use it directly
            self.abs_vector_store_path = vector_store_path
        else:
            # Combine to relative path to base path to make absolute path
            base_path: str = os.path.dirname(__file__)
            self.abs_vector_store_path = os.path.abspath(os.path.join(base_path, vector_store_path))

    async def generate_vector_store(self, loader_args: Any) -> InMemoryVectorStore:
        """
        Asynchronously loads documents from a given data source, split them into
        chunks, and build an in-memory vector store using OpenAI embeddings or
        load vectorstore from memory if it is available. 

        :param loader_args: Arguments specific to the document loader (e.g., Confluence params or PDF file paths).
        :return: In-memory vector store containing the embedded document chunks
        """
        # If vector store file path is provided (abs_vector_store_path is not None), try to load vector store first.
        if self.abs_vector_store_path:
            try:
                vectorstore = InMemoryVectorStore.load(path=self.abs_vector_store_path, embedding=OpenAIEmbeddings())
                logger.info("Loaded vector store from: %s", self.abs_vector_store_path)
                return vectorstore
            except FileNotFoundError:
                logger.error("Vector store not found at: %s. Creating from source.", self.abs_vector_store_path)

        # Load documents and build the vector store
        docs = await self.load_documents(loader_args)

        # Split documents into smaller chunks for better embedding and retrieval
        text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(chunk_size=100, chunk_overlap=50)
        doc_chunks = text_splitter.split_documents(docs)

        # Create an in-memory vector store with embeddings
        vectorstore = await InMemoryVectorStore.afrom_documents(
            documents=doc_chunks,
            collection_name="rag-in-memory",
            embedding=OpenAIEmbeddings(),
        )

        if self.save_vector_store and self.abs_vector_store_path:
            os.makedirs(os.path.dirname(self.abs_vector_store_path), exist_ok=True)
            vectorstore.dump(path=self.abs_vector_store_path)
            logger.info("Vector store saved to: %s", self.abs_vector_store_path)

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
            logger.info("Retrieval completed!")

        # Concatenate the content of all retrieved documents
        return "\n\n".join(doc.page_content for doc in results)
