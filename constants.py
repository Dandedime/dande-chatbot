from pathlib import Path

TABLE_IDX_DICT = {"VIOLATIONS":0, "CANDIDATES":1, "ELECTION_CONTRIBUTIONS": 2, "PACS_TO_CANDIDATES": 3}

TABLE_PATH_DICT = {0: Path("table_contexts/violations.txt"), 
     1: Path("table_contexts/candidates.txt"), 
     2: Path("table_contexts/election_contributions.txt"),
     3: Path("table_contexts/pacs_to_candidates.txt")
}