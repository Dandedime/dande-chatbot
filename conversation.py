from pathlib import Path
from openai import OpenAI
from build_prompts import SystemPrompt, SQLPrompt, TableSelectionPrompt
from typing import Optional, List
from abc import ABC, abstractmethod
import re

TABLE_PATH_DICT = {0: Path("table_contexts/violations.txt"), 
     1: Path("table_contexts/candidates.txt"), 
     2: Path("table_contexts/election_contributions.txt"),
     3: Path("table_contexts/pacs_to_candidates.txt")
}

def unique_messages(func):
    def wrapper(*args, **kwargs):
        messages = func(*args, **kwargs)
        unique_messages = []
        for m in messages:
            if m not in unique_messages:
                unique_messages.append(m)
        return unique_messages 
    return wrapper

class ConversationOpenAI:
    def __init__(self, api_key, model="gpt-4-0125-preview", system_prompt=None,
                 conversation_history = None, memory_window=5):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        if conversation_history is None:
            self.history = ConversationHistory(system_prompt=system_prompt, window=memory_window)

    def respond(self, messages=None):
        if messages is None:
            messages = self.history.recent_conversation
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True
        )


class AbstractDataConversation(ConversationOpenAI, ABC):
    def __init__(self, db_conn, query_prompt, answer_prompt, error_prompt,
                 empty_prompt, api_key, model="gpt-4-0125-preview",
                 conversation_history = None, memory_window=5):
        self.db_conn = db_conn
        self.query_prompt = query_prompt
        self.answer_prompt = answer_prompt
        self.error_prompt = error_prompt
        self.empty_prompt = empty_prompt

        super().__init__(api_key, model, system_prompt=self.query_prompt,
                         conversation_history=conversation_history,
                         memory_window=memory_window)

    def write_query(self):
        """Construct a db query an explanation given the current conversation"""
        return self.respond()

    def execute_query(self, response):
        """Execute the sql query in the response text if there is one"""
        query = self._extract_query(response)
        if query is not None:
            try:
                res = self.db_conn.query(query)
                return query, res, None
            except Exception as e:
                return query, None, e
        else:
            return None, None, None

    def answer(self, query, results):
        """Construct an answer to the question in the user_message given the sql query in results of the query"""
        content = self.answer_prompt.general_instructions.format(query=query, results=results)
        return self.respond(self.history.recent_conversation + [{"role": "system", "content": content}])

    def error(self, user_message, query, status):
        question = user_message["content"]
        content = self.error_prompt.general_instructions.format(question=question, query=query, error=status)
        return self.respond([{"role": "system", "content": content}])

    def empty(self, user_message, query, results):
        question = user_message["content"]
        content = self.empty_prompt.general_instructions.format(question=question, query=query, results=results)
        return self.respond([{"role": "system", "content": content}])

    @abstractmethod
    def _extract_query(self, response):
        """Extract db query from response text"""
        ...


class Neo4jConversation(AbstractDataConversation):
    def __init__(self, db_conn, api_key, model="gpt-4-0125-preview",
                 conversation_history = None, memory_window=5):
        answer_prompt = SystemPrompt.load(Path("prompt_contexts/answer.txt"))
        error_prompt = SystemPrompt.load(Path("prompt_contexts/error.txt"))
        empty_prompt = SystemPrompt.load(Path("prompt_contexts/empty.txt"))

        query_prompt =\
            SystemPrompt(Path("prompt_contexts/neo4j.txt")).general_instructions

        super().__init__(db_conn, query_prompt, answer_prompt, error_prompt,
                         empty_prompt, api_key, model,
                         conversation_history=conversation_history,
                         memory_window=memory_window)

    def _extract_query(self, response):
        """Extract neo4j query from response text"""
        print(response)
        neo4j_match = re.search(r"```cypher\n(.*)\n```", response, re.DOTALL)
        if neo4j_match:
            neo4j = neo4j_match.group(1)
            return neo4j


class SQLConversation(AbstractDataConversation):
    def __init__(self, db_conn, api_key, model="gpt-4-0125-preview", conversation_history = None, memory_window=5):
        self.db_conn = db_conn

        self.answer_prompt = SystemPrompt.load(Path("prompt_contexts/answer.txt"))
        self.error_prompt = SystemPrompt.load(Path("prompt_contexts/error.txt"))
        self.empty_prompt = SystemPrompt.load(Path("prompt_contexts/empty.txt"))

        self.system_prompt = SQLPrompt(instruction_file=Path("prompt_contexts/sql.txt"), table_files=[Path("table_contexts/violations.txt")]).system_prompt

        super().__init__(api_key, model, system_prompt=self.system_prompt, memory_window=memory_window)

    def select_tables(self, user_message):
        question = user_message["content"]
        content = self.table_selector.general_instructions + f"\nuser_message: {question}"
        return self.respond([{"role": "system", "content": content}])

    @staticmethod
    def _extract_query(response):
        """Extract sql query from response text"""
        sql_match = re.search(r"```sql\n(.*)\n```", response, re.DOTALL)
        if sql_match:
            sql = sql_match.group(1)
            return sql


class MultiDBConversation(ConversationOpenAI):
    def __init__(self, db_conversations: List[AbstractDataConversation], api_key, model="gpt-4-0125-preview", conversation_history = None, memory_window=5):
        self.db_conversations = db_conversations
        self.choos_db_prompt =\
            SystemPrompt.load("prompt_contexts/db_selection.txt")

        super().__init__(api_key=api_key, model=model,
                         system_prompt=system_prompt,
                         conversation_history=conversation_history,
                         memory_window=memory_window)

    def choose_db(self, query):
        message = {"role": "system", "content": self.choos_db_prompt}
        messages = self.history.recent_conversation + [message]
        selected_db = "".join([chunk for chunk in self.respond(messages)])
        return self.db_conversations[selected_db]


class ConversationHistory:
    def __init__(self, system_prompt=None, window=5):
        self.messages = []
        self.init_prompt = system_prompt
        if self.init_prompt is not None:
            self.messages.append({"role": "system", "content": self.init_prompt})
        self.window = window

    def append(self, message):
        self.messages.append(message)

    @property
    @unique_messages
    def recent_conversation(self):
        """List of messages including all system messages and conversation messages within the memory window"""
        # Always include the original system prompt if there is one
        if self.init_prompt is not None:
            return self.system_messages[:1] + self.messages[-(self.window-1):]  
        else:
            return self.messages[-self.window:]

    @property
    @unique_messages
    def system_messages(self):
        """List of all system and conversation messages"""
        return [message for message in self.messages if message["role"] == "system"]

    @property
    @unique_messages
    def user_messages(self):
        """List of messages from user"""
        return [message for message in self.messages if message["role"] == "user"]

    def __getitem__(self, idx):
        return self.messages[idx]
    

