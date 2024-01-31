from pathlib import Path
from openai import OpenAI
from utils import extract_sql
from build_prompts import SQLPrompt


class ConversationOpenAI:
    def __init__(self, api_key, model="gpt-4-0125-preview", memory_window=5):
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.memory_window = 5

    def respond(self, messages):
        return self.client.chat.completions.create(
            model=self.model,
            messages=messages[-self.memory_window:],
            stream=True
        )


class SQLConversation(ConversationOpenAI):
    def __init__(self, db_conn, api_key, model="gpt-4-0125-preview", memory_window=5):
        super().__init__(api_key, model, memory_window)
        self.db_conn = db_conn

        self.answer_prompt = """Given the folowing user question, the sql query, and the results of running the query, construct an answer to the question

        user question: {question}
        query: {query}
        results: {results}
        """

        self.error_prompt = """Given the following user question, sql query, and error thrown by running the query, first inform the user
        there was an error executing the query and then describe the error. Then suggest possible corrections to this query, and if something 
        in the question or query is unclear ask for further clarification from the user:
        
        user question: {question}
        query: {query}
        error: {error}
        """
        self.error_prompt = '\n'.join([line.strip() for line in self.error_prompt.strip().split('\n')])

        self.system_prompt = SQLPrompt(instruction_file=Path("prompt_contexts/sql.txt"), table_files=[Path("table_contexts/violations.txt")]).system_prompt

        self.conversation_history = ConversationHistory(self.system_prompt, recent_window=memory_window)

    def write_query(self, messages):
        """Construct a sql query with an explanation given the current conversation"""
        return self.respond(messages)

    def execute_query(self, response):
        """Execute the sql query in the response text if there is one"""
        query = extract_sql(response)
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
        content = self.answer_prompt.format(question=question, query=query, results=results)
        return self.respond([{"role": "system", "content": content}])
    
    def error(self, user_message, query, status):
        question = user_message["content"]
        content = self.error_prompt.format(question=question, query=query, error=status)
        return self.respond([{"role": "system", "content": content}])

    def _write_response(self, generator, resp_container):
        """Construct response from the generator and append to conversation history"""
        response = ""
        for chunk in generator:
            response += (chunk.choices[0].delta.content or "")
            resp_container.markdown(response)
        self.conversation_history.append({"role": "assistant", "content": response})
        return response, resp_container

    def write_full_response(self, resp_container):
        """Create the full response, including query and explanation, results of the query, and the answer to the original question"""
        response, resp_container = self._write_response(self.write_query(self.conversation_history.recent_conversation), resp_container)
        response_msg = {"role": "assistant", "content": response}
        query, results, status = self.execute_query(response)
        
        if results is not None and not results.empty: 
            print(1)
            user_message = self.conversation_history.user_messages[-1]
            response_msg["results"] = results
            answer, _ = self._write_response(self.answer(user_message, query, results), resp_container)
        elif results is not None and results.empty:
           print(2)
        if status is not None:
            print(3)
            user_message = self.conversation_history.user_messages[-1]
            answer, _ = self._write_response(self.error(user_message, query, status), resp_container)
            
            

class ConversationHistory:
    def __init__(self, system_prompt, recent_window=5):
        self.system_messages = [{"role": "system", "content": system_prompt}]
        self.messages = []
        self.recent_window = recent_window

    def append(self, message):
        if message["role"] == "system":
            self.system_messages.append(message)
        else:
            self.messages.append(message)

    @property
    def recent_conversation(self):
        """List of messages including all system messages and conversation messages within the memory window"""
        return self.system_messages + self.messages[-self.recent_window:]

    @property
    def all_messages(self):
        """List of all system and conversation messages"""
        return self.system_messages + self.messages

    @property
    def user_messages(self):
        """List of messages from user"""
        return [message for message in self.all_messages if message["role"] == "user"]

    def __getitem__(self, idx):
        return self.all_messages[idx]
