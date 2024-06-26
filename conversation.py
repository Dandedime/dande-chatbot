from pathlib import Path
from openai import AzureOpenAI
from build_prompts import SystemPrompt, SQLPrompt, TableSelectionPrompt
from constants import TABLE_PATH_DICT
from rag import PineconeIndex
from typing import List
import re

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
    def __init__(self, api_key, azure_endpoint, api_version,
                 model="entity_resolution", system_prompt=None, memory_window=5):
        self.client = AzureOpenAI(api_key=api_key,
                                  api_version=api_version,
                                  azure_endpoint=azure_endpoint)
        self.model = model
        self.history = ConversationHistory(system_prompt=system_prompt, window=memory_window)

    def respond(self, messages=None):
        if messages is None:
            messages = self.history.recent_conversation
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True
        )

class PineconeConversation(ConversationOpenAI):
   
    def __init__(self, api_key, azure_endpoint, api_version,
                 model="entity_resolution", memory_window=5): 
        self.system_prompt = SystemPrompt.from_file((Path("prompt_contexts/entity_resolution.txt"))) 
        super().__init__(api_key, azure_endpoint, api_version, model, system_prompt=self.system_prompt.general_instructions, memory_window=memory_window)

    def find_match(self, query: str, candidates: List[str]) -> List[str]:
        content = self.system_prompt.general_instructions.format(entity=query, candidates=candidates)
        return self.respond([{"role": "system", "content": content}])
    
class SQLConversation(ConversationOpenAI):
    def __init__(self, db_conn, pinecone_conn, api_key, azure_endpoint,
                 api_version, model="entity_resolution", memory_window=5):
        self.db_conn = db_conn

        self.answer_prompt = SystemPrompt.from_file(Path("prompt_contexts/answer.txt"))
        self.error_prompt = SystemPrompt.from_file(Path("prompt_contexts/error.txt"))
        self.empty_prompt = SystemPrompt.from_file(Path("prompt_contexts/empty.txt"))
    
        self.table_selector = TableSelectionPrompt.from_file(table_files=[Path("table_contexts/violations.txt"), 
                                                    Path("table_contexts/candidates.txt"), 
                                                    Path("table_contexts/election_contributions.txt"), Path("table_contexts/pacs_to_candidates.txt")])
        self.proper_nouns = PineconeIndex(pinecone_conn, "proper-nouns")

        self.system_prompt = SystemPrompt.from_file((Path("prompt_contexts/initial.txt")))

        super().__init__(api_key, azure_endpoint, api_version, model, system_prompt=self.system_prompt.general_instructions, memory_window=memory_window)

    def write_query(self, table_selection = None):
        """Construct a sql query an explanation given the current conversation"""
        if table_selection is not None:
            sql_prompt = SQLPrompt.from_file(instruction_file=Path("prompt_contexts/sql.txt"), 
                                            table_files=[TABLE_PATH_DICT[idx] for idx in table_selection])
            content = self.history.recent_conversation +[{"role": "system", "content": sql_prompt.system_prompt}]
            return self.respond(content)
        else:
            return self.respond()

    def select_tables(self, user_message):
        question = user_message["content"]
        content = self.table_selector.general_instructions + f"\nuser_message: {question}"
        return self.respond([{"role": "system", "content": content}])
    
    def verify_proper_nouns(self, query):
        return self.proper_nouns.get_similiar(query)

    def execute_query(self, response):
        """Execute the sql query in the response text if there is one"""
        query = self._extract_sql(response)
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
        proper_noun_suggestions = \
            ", ".join(self.verify_proper_nouns(user_message["content"]))
        question = user_message["content"]
        content = \
            self.empty_prompt.general_instructions.format(question=question,
                                                      query=query,
                                                      results=results,
                                                      suggestions=proper_noun_suggestions)
        return self.respond([{"role": "system", "content": content}])

    @staticmethod
    def _extract_sql(response):
        """Extract sql query from response text"""
        sql_match = re.search(r"```sql\n(.*)\n```", response, re.DOTALL)
        if sql_match:
            sql = sql_match.group(1)
            return sql


class Neo4jConversation(ConversationOpenAI):
    def __init__(self, db_conn, api_key, azure_endpoint,
                 api_version, model="entity_resolution", memory_window=5):
        self.db_conn = db_conn

        self.answer_prompt = SystemPrompt.from_file(Path("prompt_contexts/answer.txt"))
        self.error_prompt = SystemPrompt.from_file(Path("prompt_contexts/error.txt"))
        self.empty_prompt = SystemPrompt.from_file(Path("prompt_contexts/empty.txt"))
        self.system_prompt = SystemPrompt.from_file((Path("prompt_contexts/neo4j.txt")))

        super().__init__(api_key, azure_endpoint, api_version, model, system_prompt=self.system_prompt.general_instructions, memory_window=memory_window)

    def write_query(self, table_selection = None):
        """Construct a sql query an explanation given the current conversation"""
        return self.respond()

    def execute_query(self, response):
        """Execute the cypher query in the response text if there is one"""
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
        proper_noun_suggestions = \
            ", ".join(self.verify_proper_nouns(user_message["content"]))
        question = user_message["content"]
        content = \
            self.empty_prompt.general_instructions.format(question=question,
                                                      query=query,
                                                      results=results,
                                                      suggestions=proper_noun_suggestions)
        return self.respond([{"role": "system", "content": content}])

    def _extract_query(self, response):
            """Extract neo4j query from response text"""
            neo4j_match = re.search(r"```cypher\n(.*)\n```", response, re.DOTALL)
            if neo4j_match:
                neo4j = neo4j_match.group(1)
                return neo4j


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
