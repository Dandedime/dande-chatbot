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
        self.summary = self.table_description.split("\n")[0].split("The following list provides")[0]

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
    def __init__(self, prompt: str):
        self.general_instructions = prompt
    
    @classmethod
    def from_file(cls, instruction_file: Path):
        with open(instruction_file, "r") as ifile:
            prompt = ifile.read()
        return cls(prompt)


class TableSelectionPrompt(SystemPrompt):
    def __init__(self, prompt: str, table_contexts: List[TableContext]):
        self.table_contexts = table_contexts
        super().__init__(prompt.format(table_summaries="\n\n".join([table.summary for table in self.table_contexts])))
        
    @classmethod
    def from_file(cls, instruction_file: Path=Path("prompt_contexts/table_selection.txt"), table_files: Optional[List[Path]] = None):
        with open(instruction_file, "r") as ifile:
            prompt = ifile.read()
        if table_files is None:
            table_files = [Path(f) for f in glob("table_contexts/*.txt")]
        table_contexts = [TableContext(table_file) for table_file in table_files]
        return cls(prompt, table_contexts)

    def full_context(self, selected_table_idxs):
        return "\n\n".join([self.table_contexts[i].context for i in selected_table_idxs])


        
class SQLPrompt(SystemPrompt):
    def __init__(self, prompt: str, table_selection: TableSelectionPrompt):
        super().__init__(prompt)
        self.table_selection = table_selection
        self.system_prompt = self.build_system_prompt(list(range(len(table_selection.table_contexts))))

    def build_system_prompt(self, selected_table_idxs = None):
        if not selected_table_idxs:
            selected_table_idxs = []
        return self.general_instructions.format(num_tables=len(selected_table_idxs), tables_context=self.table_selection.full_context(selected_table_idxs))

    @classmethod
    def from_file(cls, instruction_file: Path, table_files: Optional[List[Path]] = None):
        table_selection = TableSelectionPrompt.from_file(table_files=table_files)
        with open(instruction_file, "r") as ifile:
            prompt = ifile.read()
        return cls(prompt, table_selection)

