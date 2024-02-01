from pathlib import Path
from glob import glob
from typing import List, Optional

import streamlit as st

SCHEMA_PATH = st.secrets.get("SCHEMA_PATH", "DATADIME1.PUBLIC")


class TableContext:
    def __init__(self, description_file: Path, schema_path=SCHEMA_PATH):
        self.table_name = f"{schema_path}.{description_file.stem.upper()}"
        with open(description_file, "r") as ifile:
            self.table_description = ifile.read()

        self.context = self._build_table_context()

    def _build_table_context(self):
        table = self.table_name.split(".")
        conn = st.connection("snowflake")
        columns = conn.query(f"""
            SELECT COLUMN_NAME, DATA_TYPE FROM {table[0].upper()}.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = '{table[1].upper()}' AND TABLE_NAME = '{table[2].upper()}'
            """, show_spinner=False,
        )
        columns = "\n".join(
            [
                f"- **{columns['COLUMN_NAME'][i]}**: {columns['DATA_TYPE'][i]}"
                for i in range(len(columns["COLUMN_NAME"]))
            ]
        )
        context = f"""
    Here is the table name <tableName> {'.'.join(table)} </tableName>

    <tableDescription>{self.table_description}</tableDescription>

    Here are the columns of the {'.'.join(table)}

    <columns>\n\n{columns}\n\n</columns>
        """
        return context

class SystemPrompt:
    def __init__(self, instruction_file: Path):
        with open(instruction_file, "r") as ifile:
            self.general_instructions = ifile.read()
    
    @classmethod
    def load(cls, instruction_file: Path):
        return cls(instruction_file)
        
class SQLPrompt(SystemPrompt):
    def __init__(self, instruction_file: Path, table_files: Optional[List[Path]] = None):
        super().__init__(instruction_file)

        if table_files is None:
            table_files = [Path(f) for f in glob("table_contexts/*.txt")]
        self.table_contexts = [TableContext(table_file) for table_file in table_files]
        self.system_prompt = self._build_system_prompt()

    def _build_system_prompt(self):
        tables_context = "\n\n".join([table.context for table in self.table_contexts])
        return self.general_instructions.format(num_tables=len(self.table_contexts), tables_context=tables_context)


# do `streamlit run prompts.py` to view the initial system prompt in a Streamlit app
if __name__ == "__main__":
    st.header("System prompt for Andy")
    prompt = SQLPrompt(Path("prompt_contexts/sql.txt"))
    st.markdown(prompt.system_prompt)
