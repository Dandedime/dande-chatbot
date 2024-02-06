from pathlib import Path
from openai import OpenAI
from build_prompts import SystemPrompt, SQLPrompt 
import re

class ConversationOpenAI:
    def __init__(self, api_key, model="gpt-4-0125-preview", system_prompt=None, memory_window=5):
        self.client = OpenAI(api_key=api_key)
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


class SQLConversation(ConversationOpenAI):
    def __init__(self, db_conn, api_key, model="gpt-4-0125-preview", memory_window=5):
        self.db_conn = db_conn

        self.answer_prompt = SystemPrompt.from_file(Path("prompt_contexts/answer.txt"))
        self.error_prompt = SystemPrompt.from_file(Path("prompt_contexts/error.txt"))
        self.empty_prompt = SystemPrompt.from_file(Path("prompt_contexts/empty.txt"))
                                                   
        self.system_prompt = SQLPrompt.from_file(instruction_file=Path("prompt_contexts/sql.txt"), table_files=[Path("table_contexts/violations.txt")]).system_prompt

        super().__init__(api_key, model, system_prompt=self.system_prompt, memory_window=memory_window)

    def write_query(self):
        """Construct a sql query an explanation given the current conversation"""
        return self.respond()

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

    def answer(self, user_message, query, results):
        """Construct an answer to the question in the user_message given the sql query in results of the query"""
        question = user_message["content"]
        content = self.answer_prompt.general_instructions.format(question=question, query=query, results=results)
        return self.respond([{"role": "system", "content": content}])
    
    def error(self, user_message, query, status):
        question = user_message["content"]
        content = self.error_prompt.general_instructions.format(question=question, query=query, error=status)
        return self.respond([{"role": "system", "content": content}])
    
    def empty(self, user_message, query, results):
        question = user_message["content"]
        content = self.empty_prompt.general_instructions.format(question=question, query=query, results=results)
        return self.respond([{"role": "system", "content": content}])

    @staticmethod
    def _extract_sql(response):
        """Extract sql query from response text"""
        sql_match = re.search(r"```sql\n(.*)\n```", response, re.DOTALL)
        if sql_match:
            sql = sql_match.group(1)
            return sql


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
    def recent_conversation(self):
        """List of messages including all system messages and conversation messages within the memory window"""
        # Always include the original system prompt if there is one
        if self.init_prompt is not None:
            return self.system_messages[:1] + self.messages[-(self.window-1):]
        else:
            return self.messages[-self.window:]

    @property
    def system_messages(self):
        """List of all system and conversation messages"""
        return [message for message in self.messages if message["role"] == "system"]

    @property
    def user_messages(self):
        """List of messages from user"""
        return [message for message in self.messages if message["role"] == "user"]


    def __getitem__(self, idx):
        return self.messages[idx]
